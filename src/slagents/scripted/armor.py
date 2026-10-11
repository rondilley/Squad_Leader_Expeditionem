"""The armor policy of the scripted agents: how a tank drives and fires (rules 28 to 41).

The tanker v3 first drove each vehicle one hex at a time towards the objective, and only for
a gain in hex distance. A building or a wood in the way gave no step a gain, so the tank
stopped there for the rest of the game, with no line of sight to a target, and its gun never
fired; and v6 had no policy for a vehicle at all. The owner watched and said: "The tanks do
not move in a sane manner and do not fire."

This policy drives a tank the way a tank commander uses one:

- It looks for a firing position: a hex with a line of sight (the core's LOS table) to an
  enemy unit within `fire_range`, at least `standoff` hexes from each enemy infantry unit,
  so a panzerfaust or a bazooka (range 3 or 4) cannot reach it.
- A tank in a firing position holds there and fires; it turns to face its target.
- A tank not in one drives along a route to the nearest one: a route field over the
  vehicle movement costs of the core (`r30_vehicle_movement.entry_cost_halves`), so it goes
  around a building or a wood and does not stop in front of it, and it pays extra for a hex
  that needs the breakdown die (rule 39.1). With no firing position on the board, the route
  goes to the objective.
- It overruns (rule 35) only a weak target: broken infantry, or one unit with no anti-tank
  weapon that the agent can see.
- A gun fires at an enemy vehicle first (rule 33.4), then at the infantry hex with the most
  unbroken units; a machine gun at infantry; a panzerfaust or a bazooka at any vehicle in
  range; infantry next to a vehicle attacks it (rule 36.1) and infantry on one attacks it in
  close combat (rule 36.2); a broken gun gets its repair die (rule 38.1).

The policy reads the state and the frame and picks one legal command, or None so that the
infantry policy of the agent decides. It is deterministic for a state and a frame.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Any, Callable

from slcore import geometry
from slcore.engine import Engine
from slcore.frame import DecisionFrame, LegalCommand
from slcore.game import (
    PHASE_ADVANCING_FIRE,
    PHASE_CLOSE_COMBAT,
    PHASE_DEFENSIVE_FIRE,
    PHASE_MOVEMENT,
    PHASE_PREP_FIRE,
    PHASE_RALLY,
    State,
)
from slcore.geometry import HexRef
from slcore.los_eval import evaluate as evaluate_los
from slcore.rules import r28_vehicles, r30_vehicle_movement, r37_at_weapons

ARMOR_FIRE_ACTIONS = ("at_fire", "afv_fire", "afv_mg", "afv_attack")
UNREACHABLE = 10**9
# The extra cost, in movement halves, of a hex that needs the breakdown die of rule 39.1,
# for each face of the die that breaks the vehicle there: a German vehicle breaks on a 5 or
# a 6 (two faces, 24 halves, two turns of a tank's movement), another army's on a 6 (12).
# An assault gun of the first version of this policy drove into a wood on its first turn
# and stood for the rest of the game. A tank goes around rough ground unless the way around
# is much longer.
BREAKDOWN_PENALTY = 12


@dataclass(frozen=True)
class ArmorParameters:
    """The named parameters of the armor policy (FR-44)."""

    armor_priority: int = 6  # what a shot at a vehicle adds over a shot at infantry
    fire_priority: int = 2  # the weight of each unbroken unit in a target hex
    standoff: int = 4  # hexes a tank keeps from enemy infantry (panzerfaust 3, bazooka 4)
    fire_range: int = 12  # the farthest target that makes a hex a firing position
    overrun: bool = True  # whether a tank drives over weak infantry (rule 35)
    pivot_to_aim: bool = True  # whether a tank that holds turns to face its target


class ArmorPolicy:
    def __init__(
        self, engine: Engine, player: int, params: ArmorParameters | None = None, objectives: Callable[[], Any] | None = None
    ) -> None:
        self.engine = engine
        self.player = player
        self.params = params or ArmorParameters()
        self._objectives = objectives or (lambda: engine.objectives(player))
        self._fields: dict[tuple, dict[HexRef, int]] = {}
        self._positions: dict[tuple, frozenset[HexRef]] = {}

    # ------------------------------------------------------------------ choose

    def choose(self, state: State, frame: DecisionFrame, by_action: dict[str, list[LegalCommand]]) -> str | None:
        phase = frame.phase
        if phase == PHASE_RALLY and "afv_repair" in by_action:
            # Rule 38.1: a gun that nobody works on stays broken for the game.
            return min(by_action["afv_repair"], key=lambda lc: lc.id).id
        if phase in (PHASE_PREP_FIRE, PHASE_DEFENSIVE_FIRE, PHASE_ADVANCING_FIRE):
            shot = self._armor_shot(state, by_action)
            if shot is not None:
                return shot
            if phase in (PHASE_PREP_FIRE, PHASE_DEFENSIVE_FIRE):
                return self._aim(state, by_action)
        if phase == PHASE_MOVEMENT:
            return self._drive(state, by_action)
        if phase == PHASE_CLOSE_COMBAT and "cc_afv" in by_action:
            # Rule 36.23: a squad that stands on a tank kills it on its firepower factor.
            return min(by_action["cc_afv"], key=lambda lc: lc.id).id
        return None

    # -------------------------------------------------------------------- fire

    def _armor_shot(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str | None:
        best: LegalCommand | None = None
        best_score: tuple[int, int] | None = None
        for action in ARMOR_FIRE_ACTIONS:
            for lc in by_action.get(action, []):
                score = self._shot_score(state, action, lc)
                if score is None:
                    continue
                if best_score is None or score > best_score or (score == best_score and best is not None and lc.id < best.id):
                    best, best_score = lc, score
        return None if best is None else best.id

    def _shot_score(self, state: State, action: str, lc: LegalCommand) -> tuple[int, int] | None:
        target = lc.command.hex
        if target is None:
            return None
        payload = dict(lc.command.extra)
        vehicle = r28_vehicles.vehicle_in(state, target)
        hostile = vehicle is not None and vehicle.player != self.player and not vehicle.wreck
        occupants = sum(1 for u in state.infantry_in(target) if u.player != self.player and not u.broken)
        if action == "at_fire":
            # Rule 37: the weapon has no other target, so it fires when it can.
            return (self.params.armor_priority * 2, 0) if hostile else None
        if action == "afv_attack":
            return (self.params.armor_priority, 0) if hostile else None
        if action == "afv_fire":
            if str(payload.get("aim")) == "vehicle":
                return (self.params.armor_priority, 0) if hostile else None
            if occupants == 0:
                return None
            return (self.params.fire_priority * occupants, occupants)
        if action == "afv_mg":
            if occupants == 0:
                return None
            return (self.params.fire_priority * occupants - 1, occupants)
        return None

    # ---------------------------------------------------------------- the picture

    def _enemies(self, state: State) -> list:
        return [u for u in state.player_units(1 - self.player) if u.hex is not None and not u.eliminated and not u.hidden and not u.wreck]

    def _enemy_infantry(self, state: State) -> list[HexRef]:
        return sorted({u.hex for u in self._enemies(state) if u.is_infantry and not u.riding})

    def _picture(self, state: State) -> tuple:
        return tuple(sorted((u.id, u.hex) for u in self._enemies(state)))

    def firing_positions(self, state: State) -> frozenset[HexRef]:
        """The hexes with a line of sight to an enemy within `fire_range` and at least
        `standoff` hexes from each enemy infantry unit."""
        key = self._picture(state)
        found = self._positions.get(key)
        if found is not None:
            return found
        engine = self.engine
        enemies = sorted({u.hex for u in self._enemies(state)})
        infantry = self._enemy_infantry(state)
        out = set()
        for here in engine.board.order:
            if any(geometry.distance(here, h) < self.params.standoff for h in infantry):
                continue
            if r30_vehicle_movement.enemy_vehicle_in(state, self.player, here) is not None:
                continue
            for target in enemies:
                if geometry.distance(here, target) > self.params.fire_range:
                    continue
                if evaluate_los(engine.board, engine.los, here, target).clear:
                    out.add(here)
                    break
        # A position on ground that needs the breakdown die (rule 39.1, the woods here) is a
        # goal only when there is no other: a German vehicle breaks down there on a 5 or a 6.
        chart = engine.vehicle_ctx.chart if engine.vehicle_ctx is not None else None
        if chart is not None:
            firm = {h for h in out if not chart.needs_breakdown_roll(engine.board.hex(h).terrain)}
            if firm:
                out = firm
        found = frozenset(out)
        self._positions = {key: found}
        return found

    def _field(self, state: State, vehicle, goals: frozenset[HexRef], blocked: frozenset[HexRef] = frozenset()) -> dict[HexRef, int]:
        """The cost in movement halves from each hex to the nearest goal, over the vehicle
        entry costs of the core, for a vehicle of this type.

        A route does not go through a hex of `blocked`, the hexes that `_best_step` does not
        enter. A route through one gave a hex a cost that no step could reach, and an
        assault gun behind a tank of its own side stood there for four turns.
        """
        key = (self._picture(state), vehicle.type_key, goals, blocked)
        found = self._fields.get(key)
        if found is not None:
            return found
        board = self.engine.board
        dist: dict[HexRef, int] = {}
        heap = [(0, g) for g in sorted(goals)]
        heapq.heapify(heap)
        while heap:
            d, here = heapq.heappop(heap)
            if here in dist:
                continue
            dist[here] = d
            if here in blocked:
                continue
            for there in board.neighbors(here):
                if there in dist:
                    continue
                if r30_vehicle_movement.enemy_vehicle_in(state, self.player, there) is not None:
                    continue
                cost = self._step_cost(state, vehicle, there, here)
                if cost is None:
                    continue
                heapq.heappush(heap, (d + cost, there))
        if len(self._fields) > 32:
            self._fields.clear()
        self._fields[key] = dist
        return dist

    def _step_cost(self, state: State, vehicle, src: HexRef, dst: HexRef) -> int | None:
        """The cost in movement halves of one step from src to dst, with the risk of the
        breakdown die of rule 39.1 as extra cost, or None when the vehicle cannot enter."""
        probe = vehicle.with_(hex=src, facing=r28_vehicles.facing_towards(src, dst))
        cost, _, breakdown = r30_vehicle_movement.entry_cost_halves(self.engine.vehicle_ctx, state, probe, dst)
        if cost is None:
            return None
        if breakdown:
            faces = 7 - r30_vehicle_movement.breakdown_number(self.engine.types, vehicle)
            cost += BREAKDOWN_PENALTY * faces
        return cost

    # ------------------------------------------------------------------- drive

    def _weak_overrun(self, state: State, dst: HexRef) -> bool:
        """Rule 35: a target worth driving over: all broken, or one unit with no AT weapon."""
        if not self.params.overrun:
            return False
        enemies = [u for u in state.infantry_in(dst) if u.player != self.player and not u.riding]
        if not enemies:
            return False
        if any(r37_at_weapons.anti_tank_weapons(state, self.engine.types, u) for u in enemies):
            return False
        return all(u.broken for u in enemies) or len(enemies) == 1

    def _drive(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str | None:
        moves: dict[int, list[LegalCommand]] = {}
        for lc in by_action.get("vehicle_move", []):
            moves.setdefault(lc.command.units[0], []).append(lc)
        if moves:
            positions = self.firing_positions(state)
            # Rule 30.8: a vehicle may not stop where another vehicle or a wreck stands, and
            # the core keeps the phase open until it leaves, so it leaves first.
            for vehicle_id in sorted(moves):
                vehicle = state.units[vehicle_id]
                if vehicle.hex is not None and r30_vehicle_movement.must_leave(state, vehicle):
                    out = self._best_step(state, vehicle, moves[vehicle_id], positions, leaving=True)
                    if out is not None:
                        return out.id
            for vehicle_id in sorted(moves):
                vehicle = state.units[vehicle_id]
                if vehicle.hex is None:
                    continue
                if vehicle.hex in positions:
                    continue  # it holds here and fires
                for lc in sorted(moves[vehicle_id], key=lambda lc: lc.id):
                    if lc.command.hex is not None and self._weak_overrun(state, lc.command.hex):
                        return lc.id
                best = self._best_step(state, vehicle, moves[vehicle_id], positions)
                if best is not None:
                    return best.id
        return self._aim(state, by_action)

    def _best_step(self, state: State, vehicle, moves: list[LegalCommand], positions: frozenset[HexRef], leaving: bool = False) -> LegalCommand | None:
        """The move one hex down the route field. With `leaving` the vehicle must leave its
        hex, so the best move goes even when it does not shorten the route."""
        # Rule 30.8: a vehicle may not stop where another working vehicle stands, so a hex
        # that holds one of this side's other vehicles is no goal and no step for this one.
        taken = frozenset(
            u.hex for u in state.player_units(self.player)
            if u.is_vehicle and u.id != vehicle.id and u.hex is not None and not u.wreck and not u.eliminated
        )
        goals = (positions or frozenset(self._objectives())) - taken
        blocked = taken | frozenset(self._enemy_infantry(state))
        field = self._field(state, vehicle, goals, blocked) if goals else {}
        # The cost of a move is the step itself (its entry cost and the risk of the breakdown
        # die) and the route from where it ends. The field holds only the route, so a step
        # into a wood that ended one hex nearer looked as good as a step on open ground, and
        # two German tanks drove into the woods on their first turn and broke down.
        best: LegalCommand | None = None
        here = field.get(vehicle.hex, UNREACHABLE)
        best_cost = 2 * UNREACHABLE + 1 if leaving else (here + 1 if here < UNREACHABLE else UNREACHABLE)
        for lc in sorted(moves, key=lambda lc: lc.id):
            dst = lc.command.hex
            if dst is None or dst in taken or r30_vehicle_movement.enemy_infantry_in(state, self.player, dst):
                continue
            rest = field.get(dst, UNREACHABLE)
            step = self._step_cost(state, vehicle, vehicle.hex, dst)
            cost = rest + (UNREACHABLE if step is None else step)
            if cost < best_cost:
                best, best_cost = lc, cost
        return best

    def _aim(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str | None:
        """Rule 30.5: a vehicle that holds turns its gun to the nearest enemy it does not cover."""
        if not self.params.pivot_to_aim:
            return None
        enemies = [u.hex for u in self._enemies(state)]
        if not enemies:
            return None
        for lc in sorted(by_action.get("vehicle_pivot", []), key=lambda lc: lc.id):
            unit = state.units[lc.command.units[0]]
            if unit.hex is None or unit.pivoted:
                continue
            near = min(enemies, key=lambda h: (geometry.distance(unit.hex, h), h))
            if r28_vehicles.in_covered_arc(unit.hex, unit.facing, near):
                continue
            facing = int(dict(lc.command.extra).get("facing", -1))
            if facing >= 0 and r28_vehicles.in_covered_arc(unit.hex, facing, near):
                return lc.id
        return None
