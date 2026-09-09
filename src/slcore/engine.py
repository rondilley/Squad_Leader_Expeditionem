"""The three public functions of the core: legal_commands, apply, hash_state.

An Engine holds the static context of one scenario on one board: the scenario, the
board, the terrain and hexside tables, the counter types, the combat tables, and the
line of sight table. It has no side effects. `new_game` makes the first state.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from slcore import geometry
from slcore.commands import Command
from slcore.events import Event
from slcore.frame import DecisionFrame, make_frame
from slcore.game import (
    PHASE_ADVANCE,
    PHASE_ADVANCING_FIRE,
    PHASE_CLOSE_COMBAT,
    PHASE_DEFENSIVE_FIRE,
    PHASE_END,
    PHASE_MOVEMENT,
    PHASE_PREP_FIRE,
    PHASE_RALLY,
    PHASE_ROUT,
    PHASE_SETUP,
    FireGroup,
    State,
)
from slcore.scenario import resolve_zone
from slcore.geometry import HexRef
from slcore.hashing import hash_state as _hash_state
from slcore.los_cache import LosTable
from slcore.los_eval import evaluate as evaluate_los
from slcore.phases import (
    AUTO,
    CONDITION_DEMO,
    CONDITION_SEWER,
    CONDITION_SMOKE,
    FIRE_PHASES,
    FIRE_WINDOW,
    PHASE_STEPS,
    SubStep,
    actor_player,
    fire_rule,
    next_phase,
    sub_step,
)
from slcore.rng import roll_die, seed_state
from slcore.rules import (
    r05_movement,
    r06_stacking,
    r08_fire,
    r10_resolution,
    r28_vehicles,
    r30_vehicle_movement,
    r31_transport,
    r32_afv_cover,
    r33_afv_combat,
    r34_afv_vs_infantry,
    r35_overrun,
    r36_infantry_vs_afv,
    r37_at_weapons,
    r38_fate,
    r13_rout,
    r14_rally,
    r15_leadership,
    r16_defensive_fire,
    r20_close_combat,
    r11_terrain,
    r21_setup,
    r22_flamethrower,
    r23_demolition,
    r24_smoke,
    r25_concealment,
    r27_sewer,
    r42_hidden,
    r44_rural,
    victory,
)
from slcore.los_eval import LosContext
from slcore.rules.r05_movement import MoveContext
from slcore.rules.r30_vehicle_movement import VehicleContext
from slcore.rules.r33_afv_combat import AMMO_AP, AMMO_HE, ArmorContext
from slcore.rules.r10_resolution import FireContext
from slcore.rules.r13_rout import RoutContext
from slcore.scenario import Scenario
from slcore.state import Board, HexsideRule, TerrainType
from slcore.tabledata import Tables
from slcore.units import KIND_CREW, KIND_LEADER, KIND_SW, KIND_VEHICLE, Unit, UnitType

RULE_4_9 = "4.9"
RULE_PR_12 = "21.2"

UNCONCEALING = {
    "move": "the unit moved",
    "stack_move": "the unit moved",
    "advance": "the unit moved",
    "rout": "the unit moved",
    "sewer_move": "the unit moved",
    "group_fire": "the unit fired",
    "ft_fire": "the unit fired",
    "place_smoke": "the unit made smoke",
    "place_demo": "the unit placed a charge",
}


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
        frame_id = self.hash_state(state)
        if state.game_over or state.phase == PHASE_END:
            return make_frame(frame_id, state.active, state.phase, "game_over", state.turn, [])
        step = self.current_step(state)
        commands = self._window_commands(state, step)
        return make_frame(frame_id, state.active, state.phase, step.name, state.turn, commands)

    def _window_commands(self, state: State, step: SubStep) -> list[Command]:
        phase = state.phase
        if phase == PHASE_SETUP:
            return self._setup_commands(state)
        if step.name == "smoke_window":
            return self._smoke_commands(state) + [Command("end_phase")]
        if step.name == "demo_window":
            return self._demo_commands(state) + [Command("end_phase")]
        if step.name == "sewer_return":
            return self._sewer_return_commands(state)
        if phase == PHASE_RALLY:
            commands = r14_rally.legal_rally_commands(state, state.active)
            if self.has_vehicles:
                # Rule 38.1 repairs a gun and rule 40.4 pushes a wreck out of the way.
                commands.extend(r38_fate.legal_repairs(state, state.active))
                commands.extend(r38_fate.legal_wreck_pushes(state, self.board, state.active))
            return commands + [Command("end_phase")]
        if phase in FIRE_PHASES:
            return self._fire_commands(state)
        if phase == PHASE_MOVEMENT:
            commands = r05_movement.legal_moves(self.move_ctx, state)
            commands.extend(self._demo_place_commands(state))
            commands.extend(self._sewer_commands(state))
            if self.has_vehicles and self.vehicle_ctx is not None:
                commands.extend(r30_vehicle_movement.legal_moves(self.vehicle_ctx, state))
                commands.extend(r31_transport.legal_boarding(state, self.types, state.active))
                commands.extend(r31_transport.legal_debarking(self.board, state, self.types, state.active))
            if self._may_end_movement(state, commands):
                commands.append(Command("end_phase"))
            return commands

        if phase == PHASE_ROUT:
            return r13_rout.legal_rout_commands(self.rout_ctx, self.types, state, state.active) + [Command("end_phase")]
        if phase == PHASE_ADVANCE:
            return r05_movement.legal_advances(self.move_ctx, state) + [Command("end_phase")]
        if phase == PHASE_CLOSE_COMBAT:
            commands = r20_close_combat.legal_declarations(state, self.types, state.active)
            if self.has_vehicles:
                # Rule 36.2: infantry that advanced onto a vehicle attacks it here.
                commands.extend(r36_infantry_vs_afv.legal_close_combat(self.board, state, self.types, state.active))
            return commands + [Command("end_phase")]
        return [Command("end_phase")]

    def _may_end_movement(self, state: State, commands: list[Command]) -> bool:
        """Rule 6.3 with rule 13.44 and project ruling PR-18.

        Rule 6.3 says the units above a stacking limit must move, so the phase does not
        end while a hex is over a limit. A broken unit cannot move in the Movement Phase,
        so a hex whose excess is broken units has no relief. Rule 13.44 removes that
        excess in the Rout Phase, and the Movement Phase must be able to reach it.

        So the window closes when no hex is over a limit, or when no command of this
        window takes a unit out of a hex that is over a limit.
        """
        if self.has_vehicles:
            # Rule 30.8: a vehicle may not stop in a hex that holds another vehicle.
            crowded = [v for v in r28_vehicles.vehicles(state, state.active) if r30_vehicle_movement.must_leave(state, v)]
            if crowded:
                ids = {v.id for v in crowded}
                if any(c.action == "vehicle_move" and c.units[0] in ids for c in commands):
                    return False
        over = r06_stacking.overstacked_hexes(state, self.types, state.active)
        if not over:
            return True
        for command in commands:
            if command.action not in ("move", "stack_move", "sewer_move"):
                continue
            if any(state.units[uid].hex in over for uid in command.units):
                return False
        return True

    def _setup_commands(self, state: State) -> list[Command]:
        """Rule 21.2 with the concealment counters that rule 25.6 gives the scenario.

        Rule 25.6 says the counters of a scenario are placed during set up, so the side
        cannot declare set up complete while it holds one.
        """
        out = r21_setup.legal_setup(self.scenario, self.board, self.types, state)
        if self.has_vehicles:
            out = self._with_vehicle_facings(state, out)
        left = r25_concealment.counters_left(state, state.active, self.concealment_allowance())
        if left <= 0:
            return out
        out = [c for c in out if c.action != "end_setup"]
        placed = {c.hex for c in state.concealment if c.player == state.active}
        for hex_ref in self._concealment_hexes(state, state.active):
            if hex_ref in placed and left < 2:
                continue
            out.append(Command("place_concealment", hex=hex_ref))
        return out

    def _with_vehicle_facings(self, state: State, commands: list[Command]) -> list[Command]:
        """Rules 29.1, 30.1, and PR-21: a vehicle is placed on a legal hex with a facing."""
        out: list[Command] = []
        for command in commands:
            if command.action != "place" or not command.units:
                out.append(command)
                continue
            unit = state.units[command.units[0]]
            if not unit.is_vehicle or command.hex is None:
                out.append(command)
                continue
            # Rule 30.1: no vehicle enters a stone building hex, and rule 29.1 puts one
            # vehicle in a hex.
            if self.board.hex(command.hex).terrain == "stone_building":
                continue
            standing = r28_vehicles.vehicle_in(state, command.hex)
            if standing is not None and standing.id != unit.id:
                continue
            for facing in range(6):
                out.append(Command("place", units=command.units, hex=command.hex, extra=(("facing", facing),)))
        return out

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

    def _smoke_commands(self, state: State) -> list[Command]:
        """Rules 24.2 and 24.3: an engineer squad puts one counter in or next to its hex."""
        out: list[Command] = []
        for unit in sorted(state.player_units(state.active), key=lambda u: u.id):
            if not r24_smoke.can_place(state, self.types, unit):
                continue
            for hex_ref in r24_smoke.target_hexes(self.board, unit):
                out.append(Command("place_smoke", units=(unit.id,), hex=hex_ref))
        return out

    def _demo_place_commands(self, state: State) -> list[Command]:
        """Rule 23.3: the charge goes on a hex next to the unit, in the Movement Phase."""
        out: list[Command] = []
        for unit in sorted(state.player_units(state.active), key=lambda u: u.id):
            if unit.hex is None or unit.carrier is not None:
                continue
            for weapon in sorted(state.carried_by(unit.id), key=lambda w: w.id):
                if not r23_demolition.can_place(state, self.types, unit, weapon):
                    continue
                for hex_ref in r23_demolition.target_hexes(self.board, unit):
                    out.append(Command("place_demo", units=(unit.id,), weapon=weapon.id, hex=hex_ref))
        return out

    def _demo_commands(self, state: State) -> list[Command]:
        """Rule 23.4: the owner explodes a charge in the Advancing Fire Phase, or does not."""
        return [
            Command("explode_demo", hex=c.hex, extra=(("charge", c.id),))
            for c in r23_demolition.ready(state, state.active)
        ]

    def _sewer_commands(self, state: State) -> list[Command]:
        """Rules 27.1, 27.2, and 27.21: the stack that may go down, and where it may come up."""
        player = state.active
        out: list[Command] = []
        for hex_ref in sorted({u.hex for u in state.player_units(player) if u.hex is not None}):
            if not r27_sewer.is_entrance(self.board, state, hex_ref):
                continue
            party = r27_sewer.party_in(state, hex_ref, player)
            if not party or not r27_sewer.party_allowed(party):
                continue
            ids = tuple(u.id for u in party)
            for target in r27_sewer.destinations(self.board, state, hex_ref):
                out.append(Command("sewer_move", units=ids, hex=target))
        return out

    def _sewer_return_commands(self, state: State) -> list[Command]:
        """Rule 27.22: the opposing player names the entrance the lost stack comes up at."""
        party = self._lost_party(state)
        if party is None:
            return [Command("end_phase")]
        out = [Command("sewer_return", hex=h) for h in r27_sewer.lost_destinations(self.board, state, party.start)]
        return out or [Command("end_phase")]

    def _lost_party(self, state: State):
        for party in state.sewer_lost:
            if party.units and state.units[party.units[0]].player == state.phasing:
                return party
        return None

    def _fire_commands(self, state: State) -> list[Command]:
        player = state.active
        rule = fire_rule(state.phase)
        out: list[Command] = []
        if state.phase == PHASE_DEFENSIVE_FIRE and state.fire_group is None:
            out.extend(r16_defensive_fire.legal_track_returns(state, player))
        group = state.fire_group
        candidates = r08_fire.firing_units(state, player)
        if group is None:
            targets = self._targets_for(state, candidates, player)
            for unit in candidates:
                for target in targets.get(unit.id, ()):  # rule 8.6, a new group at any target in sight
                    out.extend(self._add_commands(state, unit, target, rule))
                    out.extend(self._flamethrower_commands(state, unit, target, rule))
            out.extend(self._armor_fire_commands(state))
            out.append(Command("end_phase"))
            return out
        for unit in candidates:
            if unit.hex is None or not r08_fire.chain_allows(state, group, unit.hex):
                continue
            if (unit.hex, group.target) in state.fired_pairs:
                continue
            if not self._can_see(state, unit.hex, group.target):
                continue
            out.extend(self._add_commands(state, unit, group.target, rule, group))
        out.extend(self._leader_commands(state, group))
        if group.members:
            out.append(Command("group_fire"))
        return out

    # ------------------------------------------------------------------ armor windows

    def _armor_fire_commands(self, state: State) -> list[Command]:
        """Rules 33 to 38 in a fire phase: the guns, the rockets, and the tank hunters."""
        ctx = self.armor_ctx
        if ctx is None or not self.has_vehicles:
            return []
        player = state.active
        phase = state.phase
        out: list[Command] = []
        los_ctx = self._los_ctx(state)
        for vehicle in r28_vehicles.vehicles(state, player):
            if vehicle.wreck or vehicle.hex is None:
                continue
            targets = self._armor_targets(state, vehicle, los_ctx)
            if r33_afv_combat.may_fire_main(ctx, state, vehicle, phase):
                for target in targets:
                    out.extend(self._main_gun_commands(state, vehicle, target))
            if r33_afv_combat.may_fire_mg(ctx, vehicle, phase):
                for target in targets:
                    if not state.infantry_in(target):
                        continue
                    if r33_afv_combat.mg_firepower(ctx, vehicle, target, None) > 0:
                        out.append(Command("afv_mg", units=(vehicle.id,), hex=target))
            if phase == PHASE_DEFENSIVE_FIRE and not self.types[vehicle.type_key].is_turreted:
                # Rule 33.31 case I: a self-propelled gun may turn in this phase and fire.
                if not vehicle.immobilized and not vehicle.fired:
                    out.extend(r30_vehicle_movement.pivots_for(self.vehicle_ctx, state, vehicle))
        out.extend(r37_at_weapons.legal_shots(ctx, state, player, phase))
        if phase == PHASE_DEFENSIVE_FIRE:
            out.extend(r36_infantry_vs_afv.legal_attacks(self.board, state, self.types, player))
        if phase == PHASE_PREP_FIRE:
            out.extend(r38_fate.legal_smoke(ctx, state, player, phase))
        return out

    def _armor_targets(self, state: State, vehicle: Unit, los_ctx: LosContext | None) -> list[HexRef]:
        """Rule 33.1 and rule 34.1: the hexes this vehicle can shoot at."""
        if vehicle.hex is None:
            return []
        seen: list[HexRef] = []
        for hex_ref in sorted({u.hex for u in state.player_units(1 - vehicle.player) if u.hex is not None}):
            if hex_ref == vehicle.hex:
                continue
            if not any(
                (u.is_infantry and not u.hidden) or (u.is_vehicle and not u.wreck)
                for u in state.units_in(hex_ref)
                if u.player != vehicle.player
            ):
                continue
            if not self._can_see(state, vehicle.hex, hex_ref, los_ctx):
                continue
            seen.append(hex_ref)
        return seen

    def _main_gun_commands(self, state: State, vehicle: Unit, target: HexRef) -> list[Command]:
        """PR-29: one command for each shot the gun can make at this hex.

        A hex that holds a vehicle and infantry gives two commands, because rule 33.3 and
        rule 34.2 are different shots. The shell is chosen by the aim: armour piercing at a
        vehicle where the gun has it, and high explosive at infantry.
        """
        kind = self.types[vehicle.type_key]
        out: list[Command] = []
        if not kind.is_turreted and vehicle.hex is not None:
            # Rule 33.1: a vehicle fires its main armament in its covered arc. Rule 33.34
            # gives a tank the way out, and it costs case D. A self-propelled gun has no
            # turret and no way out, so the shot is not on the list at all.
            if not r28_vehicles.in_covered_arc(vehicle.hex, vehicle.facing, target):
                return out
        enemy_vehicle = r28_vehicles.vehicle_in(state, target)
        if enemy_vehicle is not None and enemy_vehicle.player != vehicle.player:
            ammo = AMMO_HE if kind.gun_he_only else AMMO_AP
            out.append(Command("afv_fire", units=(vehicle.id,), hex=target, extra=(("aim", "vehicle"), ("ammo", ammo))))
        if any(u.is_infantry and u.player != vehicle.player for u in state.units_in(target)):
            out.append(Command("afv_fire", units=(vehicle.id,), hex=target, extra=(("aim", "infantry"), ("ammo", AMMO_HE))))
            if r34_afv_vs_infantry.canister_available(self.armor_ctx, vehicle):
                distance = geometry.distance(vehicle.hex, target) if vehicle.hex else 99
                if distance <= r34_afv_vs_infantry.CANISTER_RANGE:
                    out.append(
                        Command(
                            "afv_fire",
                            units=(vehicle.id,),
                            hex=target,
                            extra=(("aim", "infantry"), ("ammo", r34_afv_vs_infantry.AMMO_CANISTER)),
                        )
                    )
        return out

    def _targets_for(self, state: State, candidates: list[Unit], player: int) -> dict[int, tuple[HexRef, ...]]:
        enemy_hexes = r10_resolution.enemy_occupied_hexes(state, player)
        los_ctx = self._los_ctx(state)
        out: dict[int, tuple[HexRef, ...]] = {}
        for unit in candidates:
            if unit.hex is None:
                continue
            out[unit.id] = tuple(
                h
                for h in enemy_hexes
                if h != unit.hex
                and (unit.hex, h) not in state.fired_pairs
                and evaluate_los(self.board, self.los, unit.hex, h, los_ctx).clear
            )
        return out

    def _los_ctx(self, state: State) -> LosContext | None:
        """Rule 32.3: the vehicles and wrecks that stand in the way this phase."""
        if not self.has_vehicles:
            return None
        hexes = r32_afv_cover.obstacle_hexes(state, state.phase)
        return LosContext(vehicles=hexes) if hexes else None

    def _can_see(self, state: State, firer: HexRef, target: HexRef, ctx: LosContext | None = None) -> bool:
        return evaluate_los(self.board, self.los, firer, target, ctx).clear

    def _add_commands(self, state: State, unit: Unit, target: HexRef, rule: str, group: FireGroup | None = None) -> list[Command]:
        out: list[Command] = []
        in_group = group is not None
        if (group is None or not r08_fire.inherent_in_group(group, unit.id)) and r08_fire.can_fire_inherent(state, self.types, unit, rule):
            if r08_fire.member_firepower(state, self.types, unit, None, target, unit.moved) is not None:
                out.append(Command("group_add", units=(unit.id,), hex=target))
        weapons_used = r08_fire.weapons_in_group(group, unit.id) if in_group else 0
        if weapons_used < r08_fire.MAX_WEAPONS_FOR_EACH_UNIT:
            for weapon in sorted(state.carried_by(unit.id), key=lambda w: w.id):
                if in_group and any(uid == unit.id and wid == weapon.id for uid, wid in group.members):
                    continue
                if not r08_fire.can_fire_weapon(state, self.types, unit, weapon, rule):
                    continue
                if r08_fire.member_firepower(state, self.types, unit, weapon, target, unit.moved) is None:
                    continue
                out.append(Command("group_add_weapon", units=(unit.id,), weapon=weapon.id, hex=target))
        return out

    def _flamethrower_commands(self, state: State, unit: Unit, target: HexRef, rule: str) -> list[Command]:
        """Rule 22.3: a flamethrower fires alone, so it is its own command and not a group."""
        if unit.hex is None:
            return []
        out: list[Command] = []
        for weapon in sorted(state.carried_by(unit.id), key=lambda w: w.id):
            if not r22_flamethrower.can_fire(state, self.types, unit, weapon, rule):
                continue
            if not r22_flamethrower.in_range(self.types, weapon, unit.hex, target):
                continue
            out.append(Command("ft_fire", units=(unit.id,), weapon=weapon.id, hex=target))
        return out

    def _leader_commands(self, state: State, group: FireGroup) -> list[Command]:
        """Rules 15.2 and 15.4 with the ruling for 15.2: one leader directs the group."""
        if group.leader is not None or not group.members:
            return []
        hexes = r08_fire.member_hexes(state, group)
        out: list[Command] = []
        per_hex: dict[HexRef, list[Unit]] = {}
        for h in hexes:
            leaders = [u for u in r15_leadership.leaders_in(state, h, state.active) if not u.directed and not u.fired]
            if not leaders:
                return []
            per_hex[h] = leaders
        for h in sorted(per_hex):
            for leader in per_hex[h]:
                out.append(Command("group_leader", units=(leader.id,)))
        return out

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
        action = command.action
        before = state
        events: list[Event] = []
        if action == "place":
            state, events = r21_setup.apply_place(state, command)
            facing = dict(command.extra).get("facing")
            if facing is not None:
                state = state.with_unit(state.units[command.units[0]].with_(facing=int(facing)))
            state, hide = self._hide_on_setup(state, command)
            events.extend(hide)
        elif action == "place_weapon":
            state, events = r21_setup.apply_place_weapon(state, command)
        elif action == "move":
            state, events = r05_movement.apply_move(self.move_ctx, state, command)
            state, ev = self._bump_into_hidden(before, state, command)
            events.extend(ev)
        elif action == "stack_move":
            state, events = r05_movement.apply_stack_move(self.move_ctx, state, command)
        elif action == "pickup":
            state, events = r05_movement.apply_pickup(self.move_ctx, state, command)
        elif action == "drop":
            state, events = r05_movement.apply_drop(self.move_ctx, state, command)
        elif action == "advance":
            state, events = r05_movement.apply_advance(self.move_ctx, state, command)
        elif action == "rally":
            state, events = r14_rally.apply_rally(state, self.types, command)
        elif action == "repair":
            state, events = r14_rally.apply_repair(state, self.types, command)
        elif action == "rout":
            state, events = r13_rout.apply_rout(self.rout_ctx, self.types, state, command)
        elif action == "stay":
            state, events = r13_rout.apply_stay(state, command)
        elif action == "track_return":
            state, events = r16_defensive_fire.apply_track_return(state, command)
        elif action in ("group_add", "group_add_weapon"):
            state, events = self._apply_group_add(state, command)
        elif action == "group_leader":
            state, events = self._apply_group_leader(state, command)
        elif action == "group_fire":
            state, events = self._apply_group_fire(state)
        elif action == "cc_attack":
            state, events = r20_close_combat.apply_declaration(state, command, state.active)
        elif action == "place_concealment":
            state, events = self._apply_place_concealment(state, command)
        elif action == "place_smoke":
            state, events = self._apply_place_smoke(state, command)
        elif action == "place_demo":
            state, events = self._apply_place_demo(state, command)
        elif action == "explode_demo":
            state, events = self._apply_explode_demo(state, command)
        elif action == "ft_fire":
            state, events = self._apply_flamethrower(state, command)
        elif action == "sewer_move":
            state, events = self._apply_sewer_move(state, command)
        elif action == "sewer_return":
            state, events = self._apply_sewer_return(state, command)
        elif action == "vehicle_move":
            state, events = self._apply_vehicle_move(state, command)
        elif action == "vehicle_pivot":
            state, events = r30_vehicle_movement.apply_pivot(self.vehicle_ctx, state, command)
        elif action == "board":
            state, events = r31_transport.apply_board(state, command)
        elif action == "debark":
            state, events = r31_transport.apply_debark(self.move_ctx, state, command)
        elif action == "afv_fire":
            state, events = self._apply_afv_fire(state, command)
        elif action == "afv_mg":
            state, events = self._apply_afv_mg(state, command)
        elif action == "at_fire":
            state, events = self._apply_at_fire(state, command)
        elif action == "afv_attack":
            state, events = r36_infantry_vs_afv.apply_defensive_attack(
                self.armor_ctx, self.fire_ctx, state, command, state.phase
            )
        elif action == "cc_afv":
            state, events = r36_infantry_vs_afv.apply_close_combat(self.armor_ctx, state, command)
        elif action == "afv_repair":
            state, events = r38_fate.apply_repair(state, command)
        elif action == "push_wreck":
            state, events = r38_fate.apply_wreck_push(state, command)
        elif action == "afv_smoke":
            state, events = r38_fate.apply_smoke(self.armor_ctx, state, command)
        elif action == "afv_dischargers":
            state, events = r38_fate.apply_dischargers(state, command)
        elif action == "end_setup":
            state = self._end_setup(state, events)
        elif action == "end_phase":
            state = self._run_from(state, state.phase, state.sub_step + 1, events)
        else:
            raise IllegalCommand("4", f"unknown action {action!r}")
        if action in UNCONCEALING:
            acting = self._acting_units(before, command)
            state, ev = self._unconceal(before, state, acting, UNCONCEALING[action])
            events.extend(ev)
            # Rule 42.2: the same acts put a hidden unit on the board.
            state, ev = r42_hidden.reveal(state, acting, UNCONCEALING[action])
            events.extend(ev)
        return state.with_(seq=state.seq + 1), events

    def _acting_units(self, before: State, command: Command) -> tuple[int, ...]:
        """The units whose action takes their concealment counter off (rule 25.4)."""
        if command.action == "group_fire":
            group = before.fire_group
            return tuple(sorted({uid for uid, _ in group.members})) if group is not None else ()
        return command.units

    def _bump_into_hidden(self, before: State, state: State, command: Command) -> tuple[State, list[Event]]:
        """Rule 42.5: a unit that walks into a hidden unit stops and ends its movement.

        The unit goes back to the hex it came from, and it has no movement factors left. It
        does not put the hidden unit on the board: rule 42.2 does that at the end of the
        Defensive Fire Phase or the Advance Phase, because the unit is next to it now.
        """
        if not command.units or command.hex is None:
            return state, []
        mover = before.units[command.units[0]]
        if mover.hex is None or not r42_hidden.enemy_hidden_in(before, command.hex, mover.player):
            return state, []
        allowance = r05_movement.allowance_halves(self.move_ctx, before, mover, leader_bonus=False)
        stopped = state.units[mover.id].with_(hex=mover.hex, mf_used=allowance, track=mover.track)
        changed = {stopped.id: stopped}
        for weapon in state.carried_by(mover.id):
            changed[weapon.id] = weapon.with_(hex=mover.hex)
        return state.with_units(changed), [
            Event(
                r42_hidden.RULE_42_5,
                "stopped",
                {
                    "unit": mover.id,
                    "hex": geometry.hex_id(*mover.hex),
                    "tried": geometry.hex_id(*command.hex),
                },
            )
        ]

    def _hide_on_setup(self, state: State, command: Command) -> tuple[State, list[Event]]:
        """Rule 42.1: the side the scenario names records a unit instead of placing it.

        Only a woods hex or a building hex holds a hidden unit. A unit of that side in any
        other hex goes on the board in full view, which is what rule 42.1 says.
        """
        side = self.scenario.hidden_side
        if not side or not command.units:
            return state, []
        unit = state.units[command.units[0]]
        sides = {self.scenario.side_index(name): name for name in self.players}
        if not r42_hidden.can_hide(side, sides, self.board, unit):
            return state, []
        hidden = unit.with_(hidden=True)
        return state.with_unit(hidden), [
            Event(
                r42_hidden.RULE_42_1,
                "hidden",
                {"unit": unit.id, "hex": geometry.hex_id(*unit.hex) if unit.hex else None},
            )
        ]

    def _unconceal(self, before: State, state: State, units: tuple[int, ...], cause: str) -> tuple[State, list[Event]]:
        places: set[tuple[HexRef, int]] = set()
        for uid in units:
            for source in (before, state):
                unit = source.units[uid]
                if unit.hex is not None:
                    places.add((unit.hex, unit.player))
        events: list[Event] = []
        for hex_ref, player in sorted(places):
            state, ev = r25_concealment.remove_in(state, hex_ref, player, r25_concealment.RULE_25_4, cause)
            events.extend(ev)
        return state, events

    def _apply_group_add(self, state: State, command: Command) -> tuple[State, list[Event]]:
        target = command.hex
        if target is None:
            raise ValueError("a fire group command needs a target hex")
        group = state.fire_group or FireGroup(target)
        member = (command.units[0], command.weapon)
        group = FireGroup(group.target, group.members + (member,), group.leader)
        rule = r08_fire.RULE_8_6 if len(group.members) > 1 else r08_fire.RULE_8_2
        return state.with_(fire_group=group), [Event(rule, "group_add", {"unit": member[0], "weapon": member[1], "target": geometry.hex_id(*target)})]

    def _apply_group_leader(self, state: State, command: Command) -> tuple[State, list[Event]]:
        group = state.fire_group
        if group is None:
            raise ValueError("no fire group is open")
        leader = command.units[0]
        return state.with_(fire_group=FireGroup(group.target, group.members, leader)), [
            Event(r15_leadership.RULE_15_2, "group_leader", {"leader": leader})
        ]

    def _apply_group_fire(self, state: State) -> tuple[State, list[Event]]:
        group = state.fire_group
        if group is None:
            raise ValueError("no fire group is open")
        pairs = set(state.fired_pairs)
        for uid, _ in group.members:
            h = state.units[uid].hex
            if h is not None:
                pairs.add((h, group.target))
        state, events = r10_resolution.resolve_group(self.fire_ctx, state, group, state.phase)
        if state.phase == PHASE_DEFENSIVE_FIRE:
            state, returned = r16_defensive_fire.return_units(state)
            events.extend(returned)
        state = state.with_(fire_group=None, fired_pairs=tuple(sorted(pairs)))
        return state, events

    def _apply_place_concealment(self, state: State, command: Command) -> tuple[State, list[Event]]:
        if command.hex is None:
            raise ValueError("a concealment counter needs a hex")
        state, counter = r25_concealment.add(state, state.active, command.hex)
        return state, [
            Event(
                r25_concealment.RULE_25_6,
                "concealed",
                {"counter": counter.id, "player": state.active, "hex": geometry.hex_id(*command.hex)},
            )
        ]

    def _apply_place_smoke(self, state: State, command: Command) -> tuple[State, list[Event]]:
        if command.hex is None:
            raise ValueError("a smoke counter needs a hex")
        return r24_smoke.place(state, command.units[0], command.hex)

    def _apply_place_demo(self, state: State, command: Command) -> tuple[State, list[Event]]:
        if command.hex is None or command.weapon is None:
            raise ValueError("a demolition charge needs a hex and a weapon")
        return r23_demolition.place(state, command.units[0], command.weapon, command.hex)

    def _apply_explode_demo(self, state: State, command: Command) -> tuple[State, list[Event]]:
        """Rules 23.1, 23.4, 23.5, 23.7, and 23.8: the charge goes off in its hex."""
        charge_id = dict(command.extra).get("charge")
        charge = next((c for c in state.demo if c.id == charge_id), None)
        if charge is None:
            raise ValueError(f"there is no demolition charge {charge_id}")
        weapon_key = state.units[charge.weapon].type_key
        state, dice = r23_demolition.roll(state)
        raw = dice[0] + dice[1]
        halves = r23_demolition.halves(self.types, weapon_key)
        drm = r11_terrain.target_hex_modifier(self.board, charge.hex)
        events = [
            Event(
                r23_demolition.RULE_23_1,
                "demo_explode",
                {
                    "charge": charge.id,
                    "hex": geometry.hex_id(*charge.hex),
                    "firepower": halves // 2,
                    "dice": list(dice),
                    "modifiers": [{"rule": r23_demolition.RULE_23_5, "value": drm, "cause": "protective cover"}],
                    "adjusted": raw + drm,
                },
            )
        ]
        state = r23_demolition.remove(state, charge.id)
        state = state.with_unit(state.units[charge.weapon].with_(eliminated=True, hex=None, carrier=None))
        if raw == r23_demolition.MALFUNCTION_ROLL:
            events.append(Event(r23_demolition.RULE_23_8, "demo_dud", {"charge": charge.id, "roll": raw}))
            return state, events
        state, hit = r10_resolution.apply_to_hex(
            self.fire_ctx, state, charge.hex, halves, raw, drm, state.phase, charge.player, affect_all=True, kill_weapons=True
        )
        events.extend(hit)
        if r27_sewer.is_entrance(self.board, state, charge.hex):
            state = r27_sewer.close(state, charge.hex)
            events.append(Event(r27_sewer.RULE_27_6, "sewer_closed", {"hex": geometry.hex_id(*charge.hex)}))
        return state, events

    def _apply_flamethrower(self, state: State, command: Command) -> tuple[State, list[Event]]:
        """Rules 22.1, 22.2, 22.6, 22.8, and 22.9: one weapon, one target, and no modifier."""
        unit_id, weapon_id, target = command.units[0], command.weapon, command.hex
        if weapon_id is None or target is None:
            raise ValueError("flamethrower fire needs a weapon and a target hex")
        halves = r22_flamethrower.halves(self.types, state.units[weapon_id])
        state, dice = r22_flamethrower.roll(state)
        raw = dice[0] + dice[1]
        events = [
            Event(
                r22_flamethrower.RULE_22_2,
                "fire",
                {
                    "target": geometry.hex_id(*target),
                    "members": [{"unit": unit_id, "weapon": weapon_id, "halves": halves, "modifiers": []}],
                    "firepower": halves // 2,
                    "dice": list(dice),
                    "modifiers": [],
                    "adjusted": raw,
                    "phase": state.phase,
                },
            )
        ]
        state = state.with_units(
            {unit_id: state.units[unit_id].with_(fired=True), weapon_id: state.units[weapon_id].with_(fired=True)}
        )
        player = state.units[unit_id].player
        state, hit = r10_resolution.apply_to_hex(
            self.fire_ctx, state, target, halves, raw, 0, state.phase, player, kill_weapons=True
        )
        events.extend(hit)
        state, fuel = r22_flamethrower.out_of_fuel(state, weapon_id, raw)
        events.extend(fuel)
        pairs = set(state.fired_pairs)
        where = state.units[unit_id].hex
        if where is not None:
            pairs.add((where, target))
        return state.with_(fired_pairs=tuple(sorted(pairs))), events

    def _apply_vehicle_move(self, state: State, command: Command) -> tuple[State, list[Event]]:
        """Rule 30 with the overrun of rule 35 and the reveal of rule 42.6."""
        vehicle_id = command.units[0]
        target = command.hex
        overrun = target is not None and r35_overrun.may_overrun(state, state.units[vehicle_id], target)
        hidden_here = target is not None and r42_hidden.enemy_hidden_in(state, target, state.units[vehicle_id].player)
        state, events = r30_vehicle_movement.apply_move(self.vehicle_ctx, state, command)
        if hidden_here and target is not None:
            # Rule 42.6: the moving player is told, the hidden unit is overrun, and it
            # loses its hidden status at once.
            state, shown = r42_hidden.reveal_in(
                state, target, None, r35_overrun.RULE_42_6, r42_hidden.RULE_42_2
            )
            events.extend(shown)
            overrun = not state.units[vehicle_id].overran
        if overrun and target is not None:
            if r35_overrun.carries_passengers(state, vehicle_id):
                # Rule 35.5: the passengers get off before the vehicle drives in.
                state, off = r31_transport.force_dismount(
                    self.board, state, vehicle_id, r35_overrun.RULE_35_5, "an overrun", charge=False
                )
                events.extend(off)
            state, ev = r35_overrun.resolve(self.armor_ctx, self.fire_ctx, state, vehicle_id, target)
            events.extend(ev)
        return state, events

    def _apply_afv_fire(self, state: State, command: Command) -> tuple[State, list[Event]]:
        """Rule 33.3 at a vehicle, or rule 34.2 at infantry."""
        extra = dict(command.extra)
        vehicle = state.units[command.units[0]]
        target = command.hex
        if target is None:
            raise ValueError("a vehicle shot needs a target hex")
        state, events = r31_transport.force_dismount(
            self.board, state, vehicle.id, r31_transport.RULE_31_7, "the vehicle fired", charge=True
        )
        if str(extra.get("aim")) == "vehicle":
            state, ev = self._resolve_gun_at_vehicle(state, vehicle, target, str(extra.get("ammo", AMMO_AP)))
        else:
            state, ev = r34_afv_vs_infantry.fire_main(
                self.armor_ctx, self.fire_ctx, state, vehicle, target, state.phase, str(extra.get("ammo", AMMO_HE))
            )
        events.extend(ev)
        return state, events

    def _resolve_gun_at_vehicle(
        self, state: State, firer: Unit, target: HexRef, ammunition: str
    ) -> tuple[State, list[Event]]:
        ctx = self.armor_ctx
        enemy = r28_vehicles.vehicle_in(state, target)
        if enemy is None:
            raise ValueError("no vehicle stands in that hex")
        hull_down = r33_afv_combat.hull_down(ctx, state, firer.hex, enemy) if firer.hex else False
        row = r28_vehicles.to_hit_row(self.board, state, enemy, hull_down)
        cases = r33_afv_combat.hit_cases(ctx, state, firer, target, state.phase, enemy.moved, bool(state.concealment_in(target)))
        state, result = r33_afv_combat.roll_to_hit(ctx, state, firer, target, row, cases)
        events = [r33_afv_combat.to_hit_event(firer, target, result)]
        state, marked = r33_afv_combat.mark_gun_fired(state, firer, result)
        events.extend(marked)
        if not result.hit:
            return state, events
        column = r33_afv_combat.kill_column_for(ctx, firer, ammunition)
        state, kill = r33_afv_combat.roll_kill(ctx, state, firer.hex, enemy, column)
        events.append(r33_afv_combat.kill_event(firer.id, enemy, kill))
        if kill.killed:
            state, ev = r33_afv_combat.destroy(ctx, state, enemy.id, "a main gun hit")
            events.extend(ev)
        elif enemy.immobilized:
            # Rule 39.3: a hit that does not destroy a vehicle already immobilized sends
            # its crew through the morale check of rule 39.2 again.
            state, ev = r33_afv_combat.crew_abandons(ctx, state, enemy.id, "rule 39.3")
            events.extend(ev)
        return state, events

    def _apply_afv_mg(self, state: State, command: Command) -> tuple[State, list[Event]]:
        vehicle = state.units[command.units[0]]
        target = command.hex
        if target is None:
            raise ValueError("a machine gun shot needs a target hex")
        state, events = r31_transport.force_dismount(
            self.board, state, vehicle.id, r31_transport.RULE_31_7, "the vehicle fired", charge=True
        )
        state, ev = r34_afv_vs_infantry.fire_mg(
            self.armor_ctx, self.fire_ctx, state, vehicle, target, state.phase
        )
        events.extend(ev)
        return state, events

    def _apply_at_fire(self, state: State, command: Command) -> tuple[State, list[Event]]:
        """Rule 37: a flamethrower, a panzerfaust, or a bazooka against a vehicle."""
        state, events = r37_at_weapons.apply_shot(self.armor_ctx, state, command, state.phase)
        weapon = state.units[command.weapon] if command.weapon is not None else None
        target = command.hex
        if weapon is not None and target is not None:
            kind = self.types[weapon.type_key].weapon_class
            if kind == r37_at_weapons.CLASS_FLAMETHROWER and state.infantry_in(target):
                # Rule 37.2: the same roll goes again on the twenty firepower column
                # against the infantry that shares the hex with the vehicle.
                firer = state.units[command.units[0]]
                state, ev = r34_afv_vs_infantry.resolve_effect(
                    self.armor_ctx,
                    self.fire_ctx,
                    state,
                    firer,
                    target,
                    r37_at_weapons.flamethrower_infantry_halves(),
                    state.phase,
                    r37_at_weapons.RULE_37_2,
                )
                events.extend(ev)
        return state, events

    def _apply_sewer_move(self, state: State, command: Command) -> tuple[State, list[Event]]:
        """Rules 27.2, 27.3, and 27.22: the stack goes down, and one die says where it arrives."""
        if command.hex is None:
            raise ValueError("sewer movement needs a destination hex")
        start = state.units[command.units[0]].hex
        if start is None:
            raise ValueError("sewer movement needs a unit on the board")
        state, events = r27_sewer.drop_heavy(state, self.types, command.units)
        rng, die = roll_die(state.rng)
        state = state.with_(rng=rng)
        state, moved = r27_sewer.send(state, command.units, start, command.hex, die)
        events.extend(moved)
        return state, events

    def _apply_sewer_return(self, state: State, command: Command) -> tuple[State, list[Event]]:
        party = self._lost_party(state)
        if party is None or command.hex is None:
            raise ValueError("no lost sewer stack is waiting")
        return r27_sewer.surface(state, party, command.hex)

    def _place_prep_fire(self, state: State) -> State:
        """Page 41 step 2.3: the Prep Fire counters go on at the end of the phase.

        Rule 4.3 then stops those units from moving, and rule 4.5 stops them from firing
        again. Within the phase rule 8.4 lets a squad fire a support weapon at a second
        hex, so the marker cannot go on when the first group resolves.
        """
        changed = {}
        for unit in state.units:
            if unit.eliminated or not (unit.is_infantry or unit.is_vehicle):
                continue
            weapons = state.carried_by(unit.id)
            if not unit.fired and not any(w.fired for w in weapons):
                continue
            # Rule 33.2 gives the counter to a vehicle as well: a vehicle that fires any
            # weapon in the Prep Fire Phase may not move in the Movement Phase.
            changed[unit.id] = unit.with_(prep_fired=True)
            for w in weapons:
                changed[w.id] = w.with_(prep_fired=True)
        return state.with_units(changed) if changed else state

    # ------------------------------------------------------------ state machine

    def _end_setup(self, state: State, events: list[Event]) -> State:
        idx = state.setup_index + 1
        events.append(Event("21.2", "setup_done", {"player": state.active}))
        if idx < len(self.scenario.setup_order):
            player = self.scenario.side_index(self.scenario.setup_order[idx])
            return state.with_(setup_index=idx, active=player)
        state, phasing = self._first_mover(state, events)
        state = state.with_(setup_index=idx, turn=1, phasing=phasing)
        state = victory.update_last_occupant(state, self.board)
        events.append(Event("4", "turn_start", {"turn": 1, "phasing": phasing}))
        return self._run_from(state, PHASE_RALLY, 0, events)

    def _first_mover(self, state: State, events: list[Event]) -> tuple[State, int]:
        """Project ruling PR-12: the card that says to roll a die gets the core generator.

        Player 0 is the side the scenario names as the first mover. A card with no roll
        gives the first player turn to that side.
        """
        if not self.scenario.first_mover_roll:
            return state, 0
        rng, die = roll_die(state.rng)
        state = state.with_(rng=rng)
        phasing = 0 if die <= 3 else 1
        events.append(Event(RULE_PR_12, "first_mover", {"die": die, "phasing": phasing}))
        return state, phasing

    def _run_from(self, state: State, phase: str, index: int, events: list[Event]) -> State:
        """Enter step `index` of `phase`, run the automatic steps, and stop at the next window."""
        while True:
            steps = PHASE_STEPS[phase]
            if index < len(steps):
                step = steps[index]
                if step.kind == AUTO:
                    state = self._auto(state, phase, step, events)
                    if state.game_over:
                        return state.with_(phase=PHASE_END, sub_step=0)
                    index += 1
                    continue
                if step.condition and not self._condition_holds(state, step):
                    index += 1
                    continue
                return state.with_(phase=phase, sub_step=index, active=actor_player(step, state.phasing))
            state = victory.update_last_occupant(state, self.board)
            following = next_phase(phase)
            if following is None:
                following = PHASE_RALLY
            events.append(Event("4", "phase", {"phase": following, "turn": state.turn, "phasing": state.phasing}))
            phase = following
            index = 0

    def _auto(self, state: State, phase: str, step: SubStep, events: list[Event]) -> State:
        name = step.name
        if name == "remove_dm":
            changed = {u.id: u.with_(dm=False, rally_tried=False) for u in state.units if u.dm or u.rally_tried}
            changed.update({u.id: u.with_(repair_tried=False) for u in state.units if u.repair_tried})
            return state.with_units(changed) if changed else state
        if name == "reset_movement":
            changed = {}
            for u in state.player_units(state.phasing):
                changed[u.id] = u.with_(mf_used=0, move_mode="", track=(), portage_max=0, mp_used=0)
            return state.with_units(changed)
        if name == "return_units":
            state, ev = r16_defensive_fire.return_units(state)
            events.extend(ev)
            return state
        if name == "place_prep_fire":
            return self._place_prep_fire(state)
        if name == "end_fire_phase":
            state = state.with_(fired_pairs=(), fire_group=None)
            if self.has_vehicles:
                # Rule 34.8: the crew exposed counter comes off at the end of the fire
                # phase of the other side.
                state, ev = r34_afv_vs_infantry.clear_exposure(state, 1 - state.phasing)
                events.extend(ev)
                if phase == PHASE_DEFENSIVE_FIRE:
                    # Rule 35.8: infantry that a vehicle stopped on top of steps to one
                    # side, immediately after this phase.
                    for vehicle in r28_vehicles.vehicles(state, state.phasing):
                        state, ev = r35_overrun.push_out(self.board, state, vehicle.id)
                        events.extend(ev)
            return state
        if name == "expire_smoke":
            state, ev = r24_smoke.expire(state, state.phasing)
            events.extend(ev)
            changed = {u.id: u.with_(made_smoke=False) for u in state.player_units(state.phasing) if u.made_smoke}
            return state.with_units(changed) if changed else state
        if name == "arm_demo":
            state, ev = r23_demolition.arm(state)
            events.extend(ev)
            return state
        if name == "concealment_adjacency":
            state, ev = r25_concealment.refresh_adjacency(state)
            events.extend(ev)
            # Rule 42.2 names the same two phases: a hidden unit next to an enemy unit
            # comes on the board at the end of a Defensive Fire Phase or an Advance Phase.
            state, ev = r42_hidden.refresh_adjacency(state, self.board)
            events.extend(ev)
            return state
        if name == "conceal_grow":
            state, ev = r25_concealment.grow(state, self.board)
            events.extend(ev)
            return state
        if name == "sewer_conceal":
            return self._sewer_conceal(state, events)
        if name == "clear_tracks":
            changed = {u.id: u.with_(track=()) for u in state.units if u.track}
            return state.with_units(changed) if changed else state
        if name == "remove_prep_fire":
            changed = {u.id: u.with_(prep_fired=False) for u in state.units if u.prep_fired}
            return state.with_units(changed) if changed else state
        if name == "rout_check":
            player = actor_player(step, state.phasing)
            state, ev = r13_rout.eliminate_hopeless(self.rout_ctx, self.types, state, player)
            events.extend(ev)
            return state
        if name == "rout_cleanup":
            state, ev = r13_rout.eliminate_overstacked_broken(self.rout_ctx, self.types, state)
            events.extend(ev)
            changed = {
                u.id: u.with_(stay=False, routed=False) for u in state.units if u.stay or u.routed
            }
            return state.with_units(changed) if changed else state
        if name == "cc_resolve":
            if state.cc_declarations:
                state, ev = r20_close_combat.resolve(state, self.types, self.tables.cc)
                events.extend(ev)
            else:
                state, ev = r20_close_combat.broken_in_melee(state)
                events.extend(ev)
                state, ev = r20_close_combat.update_melee(state)
                events.extend(ev)
            return self._check_sudden_death(state, events)
        if name == "end_player_turn":
            return self._end_player_turn(state, events)
        raise ValueError(f"unknown automatic step {name!r} in {phase}")

    def _sewer_conceal(self, state: State, events: list[Event]) -> State:
        """Rule 27.5: a stack that came up with no enemy next to it in the building is covered."""
        for unit in r27_sewer.arrivals(state, state.phasing):
            if unit.hex is None:
                continue
            if r27_sewer.same_building_enemy(self.board, state, unit.hex, unit.player):
                continue
            if any(c.hex == unit.hex and c.player == unit.player for c in state.concealment):
                continue
            state, counter = r25_concealment.add(state, unit.player, unit.hex)
            events.append(
                Event(
                    r27_sewer.RULE_27_5,
                    "concealed",
                    {"counter": counter.id, "player": unit.player, "hex": geometry.hex_id(*unit.hex)},
                )
            )
        return state

    def _end_player_turn(self, state: State, events: list[Event]) -> State:
        changed = {}
        for u in state.units:
            if u.moved or u.mf_used or u.move_mode or u.track or u.portage_max or u.stay or u.fired or u.directed or u.sewer_move or u.demo_placed or u.made_smoke:
                changed[u.id] = u.with_(
                    moved=False,
                    mf_used=0,
                    move_mode="",
                    track=(),
                    portage_max=0,
                    stay=False,
                    fired=False,
                    directed=False,
                    sewer_move=False,
                    demo_placed=False,
                    made_smoke=False,
                )
        if self.has_vehicles:
            # Rules 30.2, 33.2, 34.7, 35.8, and 31.3: what a vehicle carries into the next
            # player turn is its facing and its damage, and nothing else.
            for u in state.units:
                if not u.is_vehicle:
                    continue
                if u.mp_used or u.pivoted or u.gun_shots or u.mg_fired or u.overran or u.boarded:
                    base = changed.get(u.id, u)
                    changed[u.id] = base.with_(
                        mp_used=0, pivoted=False, gun_shots=0, mg_fired=False, overran=False, boarded=False
                    )
        state = state.with_units(changed)
        state = victory.update_last_occupant(state, self.board)
        phasing = 1 - state.phasing
        turn = state.turn
        if phasing == 0:
            turn += 1
        events.append(Event(RULE_4_9, "player_turn_end", {"turn": state.turn, "next_phasing": phasing, "next_turn": turn}))
        if turn > state.turn_limit:
            return self._finish(state.with_(phasing=phasing, turn=turn), events, "the last turn is complete")
        return state.with_(phasing=phasing, turn=turn)

    def _condition_holds(self, state: State, step: SubStep) -> bool:
        """A rare window opens only when its rule has a decision for the player."""
        player = actor_player(step, state.phasing)
        if step.condition == CONDITION_SMOKE:
            return any(r24_smoke.can_place(state, self.types, u) for u in state.player_units(player))
        if step.condition == CONDITION_DEMO:
            return bool(r23_demolition.ready(state, player))
        if step.condition == CONDITION_SEWER:
            return self._lost_party(state) is not None
        raise ValueError(f"unknown sub-step condition {step.condition!r}")

    def _check_sudden_death(self, state: State, events: list[Event]) -> State:
        """A side with no infantry counter left cannot play on, so the game ends."""
        for player in (0, 1):
            alive = [u for u in state.player_units(player) if u.hex is not None or u.carrier is not None]
            if any(u.is_infantry for u in alive):
                continue
            if any(u.is_vehicle and not u.wreck for u in alive):
                continue
            return self._finish(state, events, f"player {player} has no unit left that can fight")
        return state

    def _finish(self, state: State, events: list[Event], cause: str) -> State:
        state = victory.update_last_occupant(state, self.board)
        if not self.scenario.victory:
            events.append(Event(RULE_4_9, "game_end", {"result": "no_result", "cause": cause}))
            return state.with_(game_over=True, result="no_result", result_cause=cause)
        winner, why, results = victory.evaluate(state, self.board, self.scenario, self.types)
        events.append(
            Event(
                victory.RULE_VICTORY,
                "game_end",
                {"result": winner, "cause": f"{cause}: {why}", "conditions": [r.to_dict() for r in results]},
            )
        )
        return state.with_(game_over=True, result=winner, result_cause=f"{cause}: {why}")

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
