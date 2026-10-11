"""The harness that turns a conformance case into a state, a command, and a check.

A case names the units, the hexes, the phase, and the dice. The harness builds the
state directly, because a case is a rule situation and not a game from turn 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from slcore import geometry
from slcore.commands import Command
from slcore.engine import Engine
from slcore.game import PHASE_SETUP, Concealment, DemoCharge, SewerParty, Smoke, State
from slcore.phases import PHASE_STEPS
from slcore.rng import RngState, roll_2d6, roll_die, seed_state
from slcore.scenario import scenario_from_dict
from slcore.state import Board
from slcore.units import Unit
from sldata.loaders import load_all_counters, load_hexsides, load_tables, load_terrain

from los.fixture_board import build_fixture

SIDES = {"german": "german", "russian": "russian", "american": "american"}
MAX_SEED_SEARCH = 400000


def conformance_scenario(board: Board) -> dict[str, Any]:
    """A scenario with one hex for each side. A case builds its own state, so the set up
    areas exist only to satisfy the engine, and they must not overlap."""
    areas = {"german": ["A1"], "russian": ["A2"]}
    squad = {"german": "4-6-7", "russian": "4-4-7"}
    # One vehicle for each side, so the engine builds its armor contexts and offers the
    # command windows of rules 28 to 41. A case that names no vehicle sees no difference,
    # because a case builds the unit list of its own state.
    vehicle = {"german": "MkIVF2", "russian": "T34"}
    return {
        "id": "conformance",
        "title": "Conformance harness",
        "board": board.name,
        "turns": 6,
        "first_mover": "russian",
        "setup_order": ["german", "russian"],
        "rules_used": [str(n) for n in range(1, 42)],
        "sides": [
            {
                "side": side,
                "nationality": side,
                "groups": [
                    {
                        "id": f"{side}_all",
                        "area": {"hexes": areas[side]},
                        "units": [{"type": squad[side], "count": 1}, {"type": vehicle[side], "count": 1}],
                    }
                ],
            }
            for side in ("german", "russian")
        ],
        "victory": [],
    }


@lru_cache(maxsize=1)
def build_engine() -> Engine:
    terrain = load_terrain()
    board = build_fixture(terrain)
    scenario = scenario_from_dict(conformance_scenario(board))
    return Engine(scenario, board, terrain, load_hexsides(), load_all_counters(), load_tables())


@lru_cache(maxsize=256)
def rng_for_dice(wanted: tuple[int, ...], singles: bool = False) -> RngState:
    """A generator state whose first rolls are the wanted values.

    The case says "with dice 3 and 4", and the harness finds a state that gives them.
    No magic number goes into a case file.
    """
    for seed in range(MAX_SEED_SEARCH):
        state = seed_state(seed)
        got: list[int] = []
        ok = True
        for _ in range(len(wanted) // (1 if singles else 2)):
            if singles:
                state, value = roll_die(state)
                got.append(value)
            else:
                state, pair = roll_2d6(state)
                got.extend(pair)
        if tuple(got) == wanted:
            return seed_state(seed)
        if not ok:
            continue
    raise AssertionError(f"no seed in {MAX_SEED_SEARCH} gives the dice {wanted}")


@dataclass
class CaseState:
    engine: Engine
    state: State
    ids: dict[str, int]

    def unit(self, ref: str) -> Unit:
        return self.state.units[self.ids[ref]]

    def command(self, payload: dict[str, Any]) -> Command:
        return Command.from_payload(self.translate(payload))

    def translate(self, payload: dict[str, Any]) -> dict[str, Any]:
        out = dict(payload)
        if "units" in out:
            out["units"] = sorted(self.ids[u] if isinstance(u, str) else u for u in out["units"])
        if out.get("weapon") is not None and isinstance(out["weapon"], str):
            out["weapon"] = self.ids[out["weapon"]]
        if out.get("vehicle") is not None and isinstance(out["vehicle"], str):
            out["vehicle"] = self.ids[out["vehicle"]]
        if out.get("targets") is not None:
            out["targets"] = sorted(self.ids[u] if isinstance(u, str) else u for u in out["targets"])
        if out.get("leader") is not None and isinstance(out["leader"], str):
            out["leader"] = self.ids[out["leader"]]
        return out


def sub_step_index(phase: str, name: str, actor: str | None) -> int:
    for i, step in enumerate(PHASE_STEPS[phase]):
        if step.name == name and (actor is None or step.actor == actor):
            return i
    raise AssertionError(f"phase {phase} has no sub-step {name!r} for actor {actor!r}")


def build_case(case: dict[str, Any]) -> CaseState:
    engine = build_engine()
    base = engine.new_game(case.get("seed", 1))
    units: list[Unit] = []
    ids: dict[str, int] = {}
    for spec in case["units"]:
        ref = str(spec["ref"])
        side = str(spec["side"])
        player = engine.scenario.side_index(side)
        # A case may put a counter of another army in a seat, which is what a scenario
        # with an allied side does. `army` names the counter set and `side` names the seat.
        army = str(spec.get("army", SIDES[side]))
        type_key = f"{army}:{spec['type']}"
        kind = engine.types[type_key].kind
        uid = len(units)
        ids[ref] = uid
        units.append(
            Unit(
                id=uid,
                player=player,
                type_key=type_key,
                kind=kind,
                group=f"{side}_all",
                name=str(spec.get("name", "")),
                hex=None if spec.get("hex") is None else geometry.parse_hex_id(str(spec["hex"])),
                broken=bool(spec.get("broken", False)),
                moved=bool(spec.get("moved", False)),
                prep_fired=bool(spec.get("prep_fired", False)),
                fired=bool(spec.get("fired", False)),
                dm=bool(spec.get("dm", False)),
                malfunction=bool(spec.get("malfunction", False)),
                mf_used=int(spec.get("mf_used", 0)),
                track=tuple(geometry.parse_hex_id(str(h)) for h in spec.get("track", [])),
                portage_max=int(spec.get("portage_max", 0)),
                stay=bool(spec.get("stay", False)),
                berserk=bool(spec.get("berserk", False)),
                directed=bool(spec.get("directed", False)),
                made_smoke=bool(spec.get("made_smoke", False)),
                sewer_move=bool(spec.get("sewer_move", False)),
                demo_placed=bool(spec.get("demo_placed", False)),
                # Rules 28 to 41: the state a vehicle counter carries.
                facing=int(spec.get("facing", -1)),
                mp_used=int(spec.get("mp_used", 0)),
                wreck=bool(spec.get("wreck", False)),
                immobilized=bool(spec.get("immobilized", False)),
                crew_exposed=bool(spec.get("crew_exposed", False)),
                mg_malfunction=bool(spec.get("mg_malfunction", False)),
                disabled=bool(spec.get("disabled", False)),
                mg_disabled=bool(spec.get("mg_disabled", False)),
                pivoted=bool(spec.get("pivoted", False)),
                gun_shots=int(spec.get("gun_shots", 0)),
                mg_fired=bool(spec.get("mg_fired", False)),
                boarded=bool(spec.get("boarded", False)),
                overran=bool(spec.get("overran", False)),
                overrun_hex=None if spec.get("overrun_hex") is None else geometry.parse_hex_id(str(spec["overrun_hex"])),
                dischargers_used=bool(spec.get("dischargers_used", False)),
            )
        )
    for spec in case["units"]:
        if spec.get("carrier") is not None:
            uid = ids[str(spec["ref"])]
            carrier = ids[str(spec["carrier"])]
            units[uid] = units[uid].with_(carrier=carrier, hex=units[carrier].hex)
        if spec.get("riding") is not None:
            # Rule 31.2: the unit is on top of the vehicle counter.
            uid = ids[str(spec["ref"])]
            vehicle = ids[str(spec["riding"])]
            units[uid] = units[uid].with_(passenger_of=vehicle, hex=units[vehicle].hex)
        if spec.get("crew_of") is not None:
            # Rule 33.9: the crew counter this vehicle can put on its own wreck.
            uid = ids[str(spec["ref"])]
            units[uid] = units[uid].with_(from_wreck=ids[str(spec["crew_of"])], hex=None)
    phase = str(case.get("phase", PHASE_SETUP))
    step_name = case.get("sub_step")
    actor = case.get("actor")
    index = sub_step_index(phase, str(step_name), str(actor) if actor else None) if step_name else 0
    phasing = engine.scenario.side_index(str(case.get("phasing", "russian")))
    active = engine.scenario.side_index(str(case["active"])) if case.get("active") else None
    step = PHASE_STEPS[phase][index]
    if active is None:
        active = 1 - phasing if step.actor == "defender" else phasing
    rng = base.rng
    if case.get("dice"):
        rng = rng_for_dice(tuple(int(d) for d in case["dice"]), bool(case.get("single_dice", False)))
    state = base.with_(
        units=tuple(units),
        phase=phase,
        sub_step=index,
        phasing=phasing,
        active=active,
        turn=int(case.get("turn", 1)),
        setup_index=_setup_index(engine, phase, active, case),
        rng=rng,
        melee=tuple(geometry.parse_hex_id(str(h)) for h in case.get("melee", [])),
        last_occupant=tuple((str(k), engine.scenario.side_index(str(v))) for k, v in case.get("last_occupant", {}).items()),
        hex_occupant=tuple((str(k), engine.scenario.side_index(str(v))) for k, v in case.get("hex_occupant", {}).items()),
    )
    state = _markers(engine, state, ids, case)
    return CaseState(engine, state, ids)


def _markers(engine: Engine, state: State, ids: dict[str, int], case: dict[str, Any]) -> State:
    """The counters of rules 23, 24, 25, and 27 that a case puts on the board.

    A case names a hex and a side, and the harness gives each counter its identity, so a
    case file holds no counter number.
    """
    marker = 0
    concealment = []
    for spec in case.get("concealment", []):
        concealment.append(
            Concealment(marker, engine.scenario.side_index(str(spec["side"])), geometry.parse_hex_id(str(spec["hex"])))
        )
        marker += 1
    demo = []
    for spec in case.get("demo", []):
        demo.append(
            DemoCharge(
                marker,
                engine.scenario.side_index(str(spec["side"])),
                geometry.parse_hex_id(str(spec["hex"])),
                ids[str(spec["placer"])],
                geometry.parse_hex_id(str(spec["from"])),
                ids[str(spec["weapon"])],
                bool(spec.get("armed", False)),
            )
        )
        marker += 1
    smoke = tuple(
        Smoke(geometry.parse_hex_id(str(s["hex"])), engine.scenario.side_index(str(s["side"])))
        for s in case.get("smoke", [])
    )
    lost = tuple(
        SewerParty(tuple(sorted(ids[str(u)] for u in p["units"])), geometry.parse_hex_id(str(p["start"])))
        for p in case.get("sewer_lost", [])
    )
    left = [0, 0]
    for side, count in case.get("smoke_left", {}).items():
        left[engine.scenario.side_index(str(side))] = int(count)
    fanatic = case.get("fanatic", {})
    return state.with_(
        concealment=tuple(concealment),
        demo=tuple(demo),
        smoke=smoke,
        sewer_lost=lost,
        sewer_closed=tuple(geometry.parse_hex_id(str(h)) for h in case.get("sewer_closed", [])),
        next_marker=marker,
        smoke_left=(left[0], left[1]),
        fanatic_player=engine.scenario.side_index(str(fanatic["side"])) if fanatic.get("side") else -1,
        fanatic_hexes=tuple(geometry.parse_hex_id(str(h)) for h in fanatic.get("hexes", [])),
    )


def _setup_index(engine: Engine, phase: str, active: int, case: dict[str, Any]) -> int:
    """Which set up pass a case is in (rule 21.2).

    A case in the Set Up Phase runs in the pass of the side that acts. Every other case
    runs after set up, so the index is past the end of the set up order.
    """
    if case.get("setup_index") is not None:
        return int(case["setup_index"])
    if phase != PHASE_SETUP:
        return len(engine.scenario.setup_order)
    side = engine.scenario.players()[active]
    return engine.scenario.setup_order.index(side)


def frame_ids(cs: CaseState) -> set[str]:
    return set(cs.engine.legal_commands(cs.state).ids())


def apply_payloads(cs: CaseState, payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for payload in payloads:
        cs.state, evs = cs.engine.apply(cs.state, cs.command(payload))
        events.extend(e.to_dict() for e in evs)
    return events


def events_contain(events: list[dict[str, Any]], wanted: list[dict[str, Any]]) -> bool:
    """The wanted events appear in the log in the same sequence."""
    i = 0
    for event in events:
        if i >= len(wanted):
            break
        want = wanted[i]
        if all(event.get(k) == v for k, v in want.items() if k != "data"):
            data = want.get("data", {})
            if all(event["data"].get(k) == v for k, v in data.items()):
                i += 1
    return i >= len(wanted)
