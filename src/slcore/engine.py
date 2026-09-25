"""The three public functions of the core: legal_commands, apply, hash_state.

An Engine holds the static context of one scenario on one board: the scenario, the
board, the terrain and hexside tables, the counter types, the combat tables, and the
line of sight table. It has no side effects. `new_game` makes the first state.

The engine is a hub with no rule of its own (M3). `apply` finds the handler of the
action in the table of `slcore.actions`, which each rule module fills, and runs the
steps that follow each act: rules 25.4 and 42.2 for the acting units, the contact of
PR-32, and rule 27.5. `legal_commands` finds the generator of the window sub-step in the
same table (`slcore.windows` and `slcore.fire_window`). The phase state machine and its
automatic steps are in `slcore.turn`.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from slcore import actions, geometry, handlers, turn  # noqa: F401  (handlers fills the tables)
from slcore.commands import Command
from slcore.events import Event
from slcore.frame import DecisionFrame, make_frame
from slcore.game import PHASE_END, PHASE_SETUP, State
from slcore.geometry import HexRef
from slcore.hashing import hash_state as _hash_state
from slcore.los_cache import LosTable
from slcore.los_eval import LosContext
from slcore.los_eval import evaluate as evaluate_los
from slcore.phases import SubStep, sub_step
from slcore.rng import seed_state
from slcore.rules import (
    r06_stacking,
    r10_resolution,
    r18_berserk,
    r25_concealment,
    r28_vehicles,
    r32_afv_cover,
    r42_hidden,
    r44_rural,
)
from slcore.rules.r05_movement import MoveContext
from slcore.rules.r10_resolution import FireContext
from slcore.rules.r13_rout import RoutContext
from slcore.rules.r30_vehicle_movement import VehicleContext
from slcore.rules.r33_afv_combat import ArmorContext
from slcore.scenario import Scenario
from slcore.state import Board, HexsideRule, TerrainType
from slcore.tabledata import Tables
from slcore.units import KIND_CREW, KIND_LEADER, KIND_SW, KIND_VEHICLE, Unit, UnitType

RULE_4_9 = turn.RULE_4_9
RULE_PR_12 = turn.RULE_PR_12

# The live tables of `slcore.actions`. The import of `slcore.handlers` above filled them.
_SPECS = actions.specs()
_WINDOWS = actions.windows()


class IllegalCommand(Exception):
    def __init__(self, rule_id: str, message: str) -> None:
        super().__init__(f"{rule_id}: {message}")
        self.rule_id = rule_id
        self.message = message


class Engine:
    def __init__(
        self,
        scenario: Scenario,
        board: Board,
        terrain: Mapping[str, TerrainType],
        hexsides: Mapping[str, HexsideRule],
        counters: Mapping[str, Mapping[str, UnitType]],
        tables: Tables,
    ) -> None:
        self.scenario = scenario
        self.board = board
        self.terrain = terrain
        self.hexsides = hexsides
        self.tables = tables
        self.types: dict[str, UnitType] = {}
        for nationality, table in counters.items():
            for key, t in table.items():
                self.types[f"{nationality}:{key}"] = t
        self.move_ctx = MoveContext(board, terrain, hexsides, self.types)
        self.los = LosTable(board)
        # The last state `legal_commands` answered, and its frame.
        self._last_frame: tuple[State, DecisionFrame] | None = None
        # Rule 44.24: the crop stands from June to October. The scenario says which, and
        # the three scenarios of year one are in October.
        self.fire_ctx = FireContext(
            board,
            hexsides,
            self.types,
            tables.ift,
            self.los,
            r44_rural.wheat_in_season(dict(scenario.switches)),
        )
        self.rout_ctx = RoutContext(self.move_ctx, self.los)
        # Rules 28 to 41. A scenario with no vehicle never reaches any of this, and the
        # engine still builds the two contexts so a test can drive them directly.
        self.armor_ctx = ArmorContext(board, hexsides, self.types, tables.armor, tables.ift, self.los) if tables.armor else None
        self.vehicle_ctx = (
            VehicleContext(board, terrain, hexsides, self.types, tables.vehicle) if tables.vehicle else None
        )
        self.players = scenario.players()
        for side in scenario.sides:
            for g in side.groups:
                for entry in g.units:
                    key = f"{side.army_of(g)}:{entry.type_key}"
                    if key not in self.types:
                        raise ValueError(f"scenario {scenario.id} uses unknown counter type {key}")
                    # PR-20: a halftrack, a truck, or a jeep waits for rules 47 and 51.
                    r28_vehicles.check_class(key, self.types[key])
        self.has_vehicles = any(
            self.types[f"{side.army_of(g)}:{entry.type_key}"].is_vehicle
            for side in scenario.sides
            for g in side.groups
            for entry in g.units
        )
        if self.has_vehicles and (self.armor_ctx is None or self.vehicle_ctx is None):
            raise ValueError(
                f"scenario {scenario.id} has vehicles, and this engine was built with no armor tables"
            )
        if self.has_vehicles:
            self.fire_ctx = replace(self.fire_ctx, vehicles_in_play=True)
        self._check_setup_areas()

    def _check_setup_areas(self) -> None:
        """Each group must fit in its set up area, and the areas must not overlap."""
        seen: dict[HexRef, str] = {}
        for side in self.scenario.sides:
            for g in side.groups:
                hexes = g.area.resolve(self.board)
                if not hexes:
                    raise ValueError(f"group {g.id} of scenario {self.scenario.id} has an empty set up area")
                for h in hexes:
                    if h in seen and seen[h] != g.id:
                        raise ValueError(f"the set up areas of {seen[h]} and {g.id} share hex {geometry.hex_id(*h)}")
                    seen[h] = g.id
                infantry = 0
                squads = 0
                portage = 0
                vehicles = 0
                for entry in g.units:
                    t = self.types[f"{side.army_of(g)}:{entry.type_key}"]
                    if t.kind == KIND_SW:
                        portage += t.portage_squad_halves * entry.count
                        continue
                    if t.kind == KIND_VEHICLE:
                        vehicles += entry.count
                        continue
                    infantry += entry.count
                    if t.kind != KIND_LEADER:
                        squads += entry.count
                n = len(hexes)
                if vehicles > r06_stacking.LIMIT_VEHICLES * n:
                    raise ValueError(
                        f"group {g.id} has {vehicles} vehicles for {n} hexes, which is over the limit of rule 29.1"
                    )
                if infantry > r06_stacking.LIMIT_INFANTRY * n or squads > r06_stacking.LIMIT_SQUADS * n or portage > r06_stacking.LIMIT_PORTAGE * 2 * n:
                    raise ValueError(
                        f"group {g.id} has {infantry} infantry, {squads} squads, and {portage // 2} portage points for {n} hexes, which is over the limits of rule 6.1"
                    )

    # ---------------------------------------------------------------- new game

    def new_game(self, seed: int, switches: Mapping[str, str] | None = None) -> State:
        units: list[Unit] = []
        for player, side_name in enumerate(self.players):
            spec = self.scenario.side_spec(side_name)
            for g in spec.groups:
                for entry in g.units:
                    key = f"{spec.army_of(g)}:{entry.type_key}"
                    kind = self.types[key].kind
                    for _ in range(entry.count):
                        units.append(Unit(id=len(units), player=player, type_key=key, kind=kind, group=g.id, name=entry.name))
        # Rule 33.9: a vehicle whose wreck side has a survival number can put a crew
        # counter on the board when it dies. The counter is made here and not during the
        # game, so the unit list of a game never changes length and a trained agent keeps
        # one observation shape.
        for vehicle in [u for u in units if u.kind == KIND_VEHICLE]:
            crew_key = self._crew_key(self.types[vehicle.type_key].nationality)
            if self.types[vehicle.type_key].survival <= 0 or crew_key is None:
                continue
            units.append(
                Unit(
                    id=len(units),
                    player=vehicle.player,
                    type_key=crew_key,
                    kind=KIND_CREW,
                    group=vehicle.group,
                    name="crew",
                    from_wreck=vehicle.id,
                )
            )
        merged = dict(self.scenario.switches)
        if switches:
            merged.update({str(k): str(v) for k, v in switches.items()})
        setup_player = self.scenario.side_index(self.scenario.setup_order[0])
        fanatic_player, fanatic_hexes = self._fanatic_zone()
        return State(
            scenario_id=self.scenario.id,
            board_name=self.board.name,
            switches=tuple(sorted(merged.items())),
            seed=seed,
            turn=1,
            turn_limit=self.scenario.turns,
            phasing=0,
            phase=PHASE_SETUP,
            sub_step=0,
            active=setup_player,
            units=tuple(units),
            rng=seed_state(seed),
            seq=0,
            setup_index=0,
            smoke_left=self._smoke_allowance(),
            fanatic_player=fanatic_player,
            fanatic_hexes=fanatic_hexes,
        )

    def _crew_key(self, nationality: str) -> str | None:
        """Rule 33.9 and rule 41.2: the crew counter of this army, which fights as a squad."""
        for key, unit_type in sorted(self.types.items()):
            if unit_type.nationality == nationality and unit_type.kind == KIND_CREW:
                return key
        return None

    def _smoke_allowance(self) -> tuple[int, int]:
        """Rule 24.1: the scenario says how many counters each side has."""
        out = [0, 0]
        for name, count in self.scenario.smoke_counters:
            out[self.scenario.side_index(name)] = int(count)
        return (out[0], out[1])

    def _fanatic_zone(self) -> tuple[int, tuple[HexRef, ...]]:
        """Rule 26.2: the side and the place that the scenario makes fanatic."""
        if not self.scenario.fanatic_side:
            return -1, ()
        player = self.scenario.side_index(self.scenario.fanatic_side)
        hexes = self.scenario.fanatic_area.resolve(self.board) if self.scenario.fanatic_area else ()
        return player, tuple(sorted(hexes))

    def concealment_allowance(self) -> dict[int, int]:
        """Rule 25.6: the counters the scenario gives each side to place at set up."""
        return {self.scenario.side_index(name): int(count) for name, count in self.scenario.concealment_counters}

    def hash_state(self, state: State) -> str:
        return _hash_state(state)

    def current_step(self, state: State) -> SubStep:
        return sub_step(state.phase, state.sub_step)

    # --------------------------------------------------------- legal commands

    def legal_commands(self, state: State) -> DecisionFrame:
        """The decision frame of the state.

        A frame depends on the state and the engine only, and a frame never changes. The
        host, the agents, and `apply` each ask for the frame of the same state, so the
        engine keeps the frame of the last state it was asked for (NFR-01). It keeps one,
        so a long game does not hold a frame for each state of its history.
        """
        last = self._last_frame
        if last is not None and last[0] is state:
            return last[1]
        frame = self._build_frame(state)
        self._last_frame = (state, frame)
        return frame

    def _build_frame(self, state: State) -> DecisionFrame:
        frame_id = self.hash_state(state)
        if state.game_over or state.phase == PHASE_END:
            return make_frame(frame_id, state.active, state.phase, "game_over", state.turn, [])
        step = self.current_step(state)
        generate = _WINDOWS.get(step.name)
        commands = generate(self, state, step) if generate is not None else [Command("end_phase")]
        return make_frame(frame_id, state.active, state.phase, step.name, state.turn, commands)

    # ------------------------------------------------ queries the windows share

    def _sees_fn(self, state: State) -> r18_berserk.Sees:
        """The line of sight test of this state, with the vehicles of rule 32.3 in the way."""
        los_ctx = self._los_ctx(state)

        def sees(a: HexRef, b: HexRef) -> bool:
            return evaluate_los(self.board, self.los, a, b, los_ctx).clear

        return sees

    def _los_ctx(self, state: State) -> LosContext | None:
        """Rule 32.3: the vehicles and wrecks that stand in the way this phase."""
        if not self.has_vehicles:
            return None
        hexes = r32_afv_cover.obstacle_hexes(state, state.phase)
        return LosContext(vehicles=hexes) if hexes else None

    def _can_see(self, state: State, firer: HexRef, target: HexRef, ctx: LosContext | None = None) -> bool:
        return evaluate_los(self.board, self.los, firer, target, ctx).clear

    def _concealment_hexes(self, state: State, player: int) -> list[HexRef]:
        """Rule 25.3, rule 25.6, and project ruling PR-17.

        A counter goes on a woods hex or a building hex that is not in a set up area of the
        other side. Rule 25.6 says the counters go on the board and gives no place. Rule
        25.3 gives the terrain. A counter in the set up area of the other side is a claim
        on a hex that this side does not hold, and that is the one place it cannot go.

        The room outside the side's own units is what makes rule 25.7 work. A counter on an
        empty hex is a dummy, and the other side cannot tell it from a stack.
        """
        enemy = self.scenario.side_spec(self.players[1 - player])
        taken: set[HexRef] = set()
        for g in enemy.groups:
            taken.update(g.area.resolve(self.board))
        return sorted(
            h.ref
            for h in self.board
            if h.ref not in taken and r25_concealment.hex_allows_concealment(self.board, h.ref)
        )

    def _blind_hexes(self, state: State, player: int) -> frozenset[HexRef]:
        """Rule 42.4 with PR-52: the hexes this player may fire blind into.

        Only when the scenario gives the other side hidden initial placement. A hex is a
        woods or building hex (rule 42.1) with no unit of this player's side and no enemy
        the player knows of, because a known enemy hex is a target already. The set reads
        no hidden unit, so it is the same whether a hidden unit is there or not.
        """
        hidden_side = self.scenario.hidden_side
        if not hidden_side or self.players[1 - player] != hidden_side:
            return frozenset()
        known = r10_resolution.enemy_occupied_hexes(state, player)
        return r42_hidden.blind_fire_hexes(self.board, state, player, known)

    # ------------------------------------------------------------------ apply

    def apply(self, state: State, command: Command, frame: DecisionFrame | None = None) -> tuple[State, list[Event]]:
        """Apply one legal command.

        A caller that already built the frame for this state may pass it. The core
        compares its frame ID with the hash of the state, so a stale frame is refused
        and the core still decides what is legal.
        """
        if frame is None or frame.frame_id != self.hash_state(state):
            frame = self.legal_commands(state)
        legal = frame.by_id(command.id)
        if legal is None:
            rule_id = RULE_4_9 if state.game_over else self.current_step(state).rule_id
            raise IllegalCommand(rule_id, f"command {command.payload()} is not legal in {state.phase}/{frame.sub_step}")
        # The core applies its own copy of the command. Two payloads with one ID, such as
        # the same units in a different sequence, then give one state and one hash.
        command = legal.command
        spec = _SPECS.get(command.action)
        if spec is None:
            raise IllegalCommand("4", f"unknown action {command.action!r}")
        before = state
        state, events = spec.apply(self, state, command)
        if spec.unconceals:
            acting = spec.acting_units(before, command)
            state, ev = r25_concealment.unconceal(before, state, acting, spec.unconceals)
            events.extend(ev)
            # Rule 42.2: the same acts put a hidden unit on the board.
            state, ev = r42_hidden.reveal(state, acting, spec.unconceals)
            events.extend(ev)
        # PR-32: an entry into the hex of a hidden unit puts it on the board at once.
        state, ev = r42_hidden.reveal_contact(state)
        events.extend(ev)
        if spec.conceal_on_arrival:
            # Rule 27.5 and PR-35: the stack is covered at the moment it arrives.
            state = turn.sewer_conceal(self, state, events)
        return state.with_(seq=state.seq + 1), events

    # ---------------------------------------------------------------- helpers

    def objectives(self, player: int) -> tuple[HexRef, ...]:
        """The set up areas of the enemy groups the scenario marks, plus the scenario objectives."""
        enemy = self.scenario.side_spec(self.players[1 - player])
        out: list[HexRef] = list(self.scenario.objectives)
        for g in enemy.groups:
            if g.objective:
                out.extend(g.area.resolve(self.board))
        return tuple(sorted(set(out)))

    def replay(self, seed: int, payloads: list[Mapping[str, Any]], switches: Mapping[str, str] | None = None) -> list[str]:
        """Apply each logged payload and give the hash after each."""
        state = self.new_game(seed, switches)
        hashes: list[str] = []
        for payload in payloads:
            state, _ = self.apply(state, Command.from_payload(payload))
            hashes.append(self.hash_state(state))
        return hashes


def describe_unit(engine: Engine, u: Unit) -> str:
    t = engine.types[u.type_key]
    where = "-" if u.hex is None else geometry.hex_id(*u.hex)
    if u.kind == KIND_LEADER:
        return f"{u.id}:{u.name or t.key}@{where}"
    return f"{u.id}:{t.key}@{where}"
