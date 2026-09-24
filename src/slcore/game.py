"""The game state (AR-03). A frozen record; `apply` gives a new one."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from slcore.geometry import HexRef
from slcore.rng import RngState
from slcore.units import Unit


@dataclass(frozen=True)
class FireGroup:
    """Rule 8.6: the fire group under formation. A member is (unit id, weapon id or None for inherent fire)."""

    target: HexRef
    members: tuple[tuple[int, int | None], ...] = ()
    leader: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"target": list(self.target), "members": [list(m) for m in self.members], "leader": self.leader}

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "FireGroup":
        return FireGroup((int(d["target"][0]), int(d["target"][1])), tuple((int(m[0]), None if m[1] is None else int(m[1])) for m in d["members"]), None if d.get("leader") is None else int(d["leader"]))


@dataclass(frozen=True)
class CcDeclaration:
    """Rule 20.4: one declared close combat attack."""

    player: int
    attackers: tuple[int, ...]
    targets: tuple[int, ...]
    leader: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"player": self.player, "attackers": list(self.attackers), "targets": list(self.targets), "leader": self.leader}

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "CcDeclaration":
        return CcDeclaration(int(d["player"]), tuple(int(x) for x in d["attackers"]), tuple(int(x) for x in d["targets"]), None if d.get("leader") is None else int(d["leader"]))


@dataclass(frozen=True)
class Smoke:
    """Rule 24: one smoke counter. Rule 24.8 removes it at the next Prep Fire Phase of its owner."""

    hex: HexRef
    player: int

    def to_dict(self) -> dict[str, Any]:
        return {"hex": list(self.hex), "player": self.player}

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "Smoke":
        return Smoke((int(d["hex"][0]), int(d["hex"][1])), int(d["player"]))


@dataclass(frozen=True)
class Concealment:
    """Rule 25: one concealment counter. A counter with no unit below it is a dummy (rule 25.7).

    The counter has its own identity, so a view gives the opponent a stable token and
    never the units below it (AR-09).
    """

    id: int
    player: int
    hex: HexRef

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "player": self.player, "hex": list(self.hex)}

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "Concealment":
        return Concealment(int(d["id"]), int(d["player"]), (int(d["hex"][0]), int(d["hex"][1])))


@dataclass(frozen=True)
class DemoCharge:
    """Rule 23: one demolition charge on its target hex.

    `placed_from` is the hex of the unit that placed it, because rule 23.3 keeps the
    charge unexploded when that unit breaks in that hex. `armed` becomes true when the
    placing unit lives through the Defensive Fire Phase without breaking.
    """

    id: int
    player: int
    hex: HexRef
    placer: int
    placed_from: HexRef
    weapon: int
    armed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "player": self.player,
            "hex": list(self.hex),
            "placer": self.placer,
            "placed_from": list(self.placed_from),
            "weapon": self.weapon,
            "armed": self.armed,
        }

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "DemoCharge":
        return DemoCharge(
            int(d["id"]),
            int(d["player"]),
            (int(d["hex"][0]), int(d["hex"][1])),
            int(d["placer"]),
            (int(d["placed_from"][0]), int(d["placed_from"][1])),
            int(d["weapon"]),
            bool(d.get("armed", False)),
        )


@dataclass(frozen=True)
class SewerParty:
    """Rule 27.22: a stack that became lost in the sewer.

    The stack is off the board. In its next Movement Phase the opposing player names a
    sewer entrance within six hexes of `start`, and the stack comes back there.
    """

    units: tuple[int, ...]
    start: HexRef

    def to_dict(self) -> dict[str, Any]:
        return {"units": list(self.units), "start": list(self.start)}

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "SewerParty":
        return SewerParty(tuple(int(u) for u in d["units"]), (int(d["start"][0]), int(d["start"][1])))


# The name of the memo that `State._index` keeps. It is not a field of the record.
INDEX_ATTRIBUTE = "_unit_index"

PHASE_SETUP = "setup"
PHASE_RALLY = "rally"
PHASE_PREP_FIRE = "prep_fire"
PHASE_MOVEMENT = "movement"
PHASE_DEFENSIVE_FIRE = "defensive_fire"
PHASE_ADVANCING_FIRE = "advancing_fire"
PHASE_ROUT = "rout"
PHASE_ADVANCE = "advance"
PHASE_CLOSE_COMBAT = "close_combat"
PHASE_END = "end"

def _two(values: Any) -> tuple[int, int]:
    """The smoke allowance of the two players (rule 24.1)."""
    out = [int(v) for v in values]
    while len(out) < 2:
        out.append(0)
    return (out[0], out[1])


PLAYER_TURN_PHASES = (
    PHASE_RALLY,
    PHASE_PREP_FIRE,
    PHASE_MOVEMENT,
    PHASE_DEFENSIVE_FIRE,
    PHASE_ADVANCING_FIRE,
    PHASE_ROUT,
    PHASE_ADVANCE,
    PHASE_CLOSE_COMBAT,
)


@dataclass(frozen=True)
class State:
    scenario_id: str
    board_name: str
    switches: tuple[tuple[str, str], ...]
    seed: int
    turn: int
    turn_limit: int
    phasing: int
    phase: str
    sub_step: int
    active: int
    units: tuple[Unit, ...]
    rng: RngState
    seq: int
    setup_index: int
    game_over: bool = False
    result: str = ""
    result_cause: str = ""
    fire_group: FireGroup | None = None
    cc_declarations: tuple[CcDeclaration, ...] = ()
    melee: tuple[HexRef, ...] = ()
    last_occupant: tuple[tuple[str, int], ...] = ()
    hex_occupant: tuple[tuple[str, int], ...] = ()
    fired_pairs: tuple[tuple[HexRef, HexRef], ...] = ()
    smoke: tuple[Smoke, ...] = ()
    concealment: tuple[Concealment, ...] = ()
    demo: tuple[DemoCharge, ...] = ()
    sewer_lost: tuple[SewerParty, ...] = ()
    sewer_closed: tuple[HexRef, ...] = ()
    next_marker: int = 0
    smoke_left: tuple[int, int] = (0, 0)
    fanatic_player: int = -1
    fanatic_hexes: tuple[HexRef, ...] = ()
    # Rules 37.35 and 37.46: each anti-tank shot this player turn, as firer id and class.
    at_shots: tuple[tuple[int, str], ...] = ()

    @property
    def defender(self) -> int:
        return 1 - self.phasing

    def unit(self, unit_id: int) -> Unit:
        return self.units[unit_id]

    def with_(self, **changes: Any) -> "State":
        return replace(self, **changes)

    def with_unit(self, unit: Unit) -> "State":
        units = list(self.units)
        units[unit.id] = unit
        return replace(self, units=tuple(units))

    def with_units(self, changed: Mapping[int, Unit]) -> "State":
        units = list(self.units)
        for uid, u in changed.items():
            units[uid] = u
        return replace(self, units=tuple(units))

    def _index(self) -> tuple[dict[HexRef, tuple[Unit, ...]], dict[int, tuple[Unit, ...]]]:
        """The units of this state by hex and by carrier, built one time for each state.

        `units_in` and `carried_by` are the two hottest reads of the core: the movement
        window asks for the load of a hex for each destination it offers. A walk of the
        unit list for each of them is the largest single cost of an environment step
        (NFR-01). A state never changes, so the index is built one time and kept on the
        object. The memo is not a field, so it is not in the state document, the equality,
        or a copy made with `with_`, in the same way the state hash is not.
        """
        found = getattr(self, INDEX_ATTRIBUTE, None)
        if found is None:
            by_hex: dict[HexRef, list[Unit]] = {}
            by_carrier: dict[int, list[Unit]] = {}
            for u in self.units:
                if u.eliminated:
                    continue
                if u.carrier is None:
                    if u.hex is not None:
                        by_hex.setdefault(u.hex, []).append(u)
                else:
                    by_carrier.setdefault(u.carrier, []).append(u)
            found = (
                {k: tuple(v) for k, v in by_hex.items()},
                {k: tuple(v) for k, v in by_carrier.items()},
            )
            object.__setattr__(self, INDEX_ATTRIBUTE, found)
        return found

    def units_in(self, hex_ref: HexRef) -> tuple[Unit, ...]:
        return self._index()[0].get(hex_ref, ())

    def carried_by(self, unit_id: int) -> tuple[Unit, ...]:
        return self._index()[1].get(unit_id, ())

    def player_units(self, player: int) -> tuple[Unit, ...]:
        return tuple(u for u in self.units if u.player == player and not u.eliminated)

    def infantry_in(self, hex_ref: HexRef) -> tuple[Unit, ...]:
        return tuple(u for u in self.units_in(hex_ref) if u.is_infantry)

    def in_melee(self, hex_ref: HexRef | None) -> bool:
        return hex_ref is not None and hex_ref in self.melee

    def smoke_in(self, hex_ref: HexRef | None) -> bool:
        return hex_ref is not None and any(s.hex == hex_ref for s in self.smoke)

    def concealment_in(self, hex_ref: HexRef | None) -> tuple[Concealment, ...]:
        if hex_ref is None:
            return ()
        return tuple(c for c in self.concealment if c.hex == hex_ref)

    def concealed(self, unit: Unit) -> bool:
        """Rule 25.2: a unit below a concealment counter of its own side."""
        if unit.hex is None or unit.carrier is not None:
            return False
        return any(c.hex == unit.hex and c.player == unit.player for c in self.concealment)

    def demo_in(self, hex_ref: HexRef | None) -> tuple[DemoCharge, ...]:
        if hex_ref is None:
            return ()
        return tuple(d for d in self.demo if d.hex == hex_ref)

    def fanatic(self, unit: Unit) -> bool:
        """Rule 26.2: the benefit belongs to one side and to a place, not to a counter."""
        return unit.player == self.fanatic_player and unit.hex is not None and unit.hex in self.fanatic_hexes

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "board_name": self.board_name,
            "switches": [list(kv) for kv in self.switches],
            "seed": self.seed,
            "turn": self.turn,
            "turn_limit": self.turn_limit,
            "phasing": self.phasing,
            "phase": self.phase,
            "sub_step": self.sub_step,
            "active": self.active,
            "units": [u.to_dict() for u in self.units],
            "rng": list(self.rng),
            "seq": self.seq,
            "setup_index": self.setup_index,
            "game_over": self.game_over,
            "result": self.result,
            "result_cause": self.result_cause,
            "fire_group": None if self.fire_group is None else self.fire_group.to_dict(),
            "cc_declarations": [c.to_dict() for c in self.cc_declarations],
            "melee": [list(h) for h in self.melee],
            "last_occupant": [[b, p] for b, p in self.last_occupant],
            "hex_occupant": [[h, p] for h, p in self.hex_occupant],
            "fired_pairs": [[list(a), list(b)] for a, b in self.fired_pairs],
            "smoke": [x.to_dict() for x in self.smoke],
            "concealment": [x.to_dict() for x in self.concealment],
            "demo": [x.to_dict() for x in self.demo],
            "sewer_lost": [x.to_dict() for x in self.sewer_lost],
            "sewer_closed": [list(h) for h in self.sewer_closed],
            "next_marker": self.next_marker,
            "smoke_left": list(self.smoke_left),
            "fanatic_player": self.fanatic_player,
            "fanatic_hexes": [list(h) for h in self.fanatic_hexes],
            "at_shots": [[fid, weapon_class] for fid, weapon_class in self.at_shots],
        }

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "State":
        rng = d["rng"]
        return State(
            scenario_id=str(d["scenario_id"]),
            board_name=str(d["board_name"]),
            switches=tuple((str(k), str(v)) for k, v in d["switches"]),
            seed=int(d["seed"]),
            turn=int(d["turn"]),
            turn_limit=int(d["turn_limit"]),
            phasing=int(d["phasing"]),
            phase=str(d["phase"]),
            sub_step=int(d["sub_step"]),
            active=int(d["active"]),
            units=tuple(Unit.from_dict(u) for u in d["units"]),
            rng=(int(rng[0]), int(rng[1]), int(rng[2]), int(rng[3])),
            seq=int(d["seq"]),
            setup_index=int(d["setup_index"]),
            game_over=bool(d.get("game_over", False)),
            result=str(d.get("result", "")),
            result_cause=str(d.get("result_cause", "")),
            fire_group=None if d.get("fire_group") is None else FireGroup.from_dict(d["fire_group"]),
            cc_declarations=tuple(CcDeclaration.from_dict(c) for c in d.get("cc_declarations", [])),
            melee=tuple((int(h[0]), int(h[1])) for h in d.get("melee", [])),
            last_occupant=tuple((str(b), int(p)) for b, p in d.get("last_occupant", [])),
            hex_occupant=tuple((str(h), int(p)) for h, p in d.get("hex_occupant", [])),
            fired_pairs=tuple(((int(a[0]), int(a[1])), (int(b[0]), int(b[1]))) for a, b in d.get("fired_pairs", [])),
            smoke=tuple(Smoke.from_dict(x) for x in d.get("smoke", [])),
            concealment=tuple(Concealment.from_dict(x) for x in d.get("concealment", [])),
            demo=tuple(DemoCharge.from_dict(x) for x in d.get("demo", [])),
            sewer_lost=tuple(SewerParty.from_dict(x) for x in d.get("sewer_lost", [])),
            sewer_closed=tuple((int(h[0]), int(h[1])) for h in d.get("sewer_closed", [])),
            next_marker=int(d.get("next_marker", 0)),
            smoke_left=_two(d.get("smoke_left", (0, 0))),
            fanatic_player=int(d.get("fanatic_player", -1)),
            fanatic_hexes=tuple((int(h[0]), int(h[1])) for h in d.get("fanatic_hexes", [])),
            at_shots=tuple((int(pair[0]), str(pair[1])) for pair in d.get("at_shots", [])),
        )
