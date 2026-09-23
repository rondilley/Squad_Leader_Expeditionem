"""Scripted agent v6: the tempo agent. The attacker keeps to a schedule.

The first gauntlet run (VIBE_HISTORY, 2026-09-12) put v1 above v4 and v5 on scenario 1,
and a random agent won one game in three against each of them. The probe of those games
found one cause. Agent v4 scores a move as the gain toward the objective, minus the threat
of the destination hex. The threat is in firepower halves, so a street hex that three
German squads can see is worth minus 24, and one hex of gain is worth plus 2 or 3. No move
has a positive score, so the attacker moves on turn 1 and then stands still for the rest
of the game. Agent v5 inherits the score. A random German wins scenario 1 against each of
them, because the Russians never arrive.

Agent v6 changes nine things. The first two are the load-bearing rules of an attack with
a time limit (FM 3-90, the tempo of the offense; RV-9 section 4). The other seven came out
of the probe of the games, one at a time, and each one names the defect it corrects.

1. The threat is in squads, not in firepower halves. One squad of four firepower is eight
   halves, so the threat divides by `threat_scale`. Three squads that see a hex are a threat
   of three. A covered hex halves it, and open ground doubles it, because rule 16.5 gives the
   fire at a unit that moves in the open a minus two. The threat then multiplies by the size
   of the stack that moves, because a KIA result of rule 8.8 removes the whole stack and a
   morale check falls on each unit of it. So the agent moves single units across the open
   and stacks them in cover, which is dispersion. A hex of gain in cover is worth the risk
   of two squads that see it, which is the trade a real attacker makes.

2. The schedule. A side with a positional victory condition (a building, a hex, or a sole
   occupant at game end) has a deadline. For each unit, the turns left minus the turns the
   fastest route to its target needs is its slack. When the slack falls below
   `schedule_margin`, the unit is pressed: each move with a gain toward the objective beats
   a stand, and the threat and the cover only order the moves with a gain. A defender has no
   positional condition of its own, so it is never pressed and keeps the v5 play.

3. The maneuver element does not prep fire. Rule 8.1 holds a unit that fired in the Prep
   Fire Phase in its hex for the turn. Agent v1 fires with each unit that has a target, so
   on the turn the schedule says go, the unit has already fired and cannot move. That is the
   second half of the frozen attacker. In v6 a pressed unit stays out of the prep fire
   groups, so the base of fire is the units with time to spare and the maneuver element
   keeps its move (FM 3-21.8, the two elements of fire and movement).

4. A move keeps the stacking limit. Agent v1 scores each unit on its own, so three units
   in a row select the same covered hex, the fourth makes it over the limit of rule 6.1,
   and the relief of rule 6.3 then moves the unit out by its id and not by its safety. The
   probe found a stack of three squads sent into an open street that way, and a KIA took
   the stack. In v6 a step into a hex that the units would put over the limit is out of the
   list, and the relief takes the safest step out.

5. The route. Agent v1 measures the gain of a step as the change of the hex distance to
   the objective, so it walks the straight line, and the straight line in a city is the
   street. Agent v6 measures the gain on a route field: the least cost from each hex to
   the target, where the cost of a step is the movement cost of rule 5.5 plus the threat of
   the hex it enters, weighted by `route_risk`. So a covered approach that is two hexes
   longer beats a street that a machine gun covers, which is the covered and concealed
   route of the doctrine. A pressed unit reads a second field with no risk in it, the
   fastest route, because the schedule leaves no time for the detour. The slack of a unit
   is the turns left minus the turns the fastest route needs at its movement allowance.
   The fields are computed one time for each change of the enemy picture (its turn, its
   phase, and where its unbroken units stand) and read from a cache.

6. A stand is a choice too. Agent v1 moves when a step has a positive score and stands
   otherwise, so a stack in a beaten zone with no good step forward stands in the beaten
   zone. Agent v6 scores the stand as a step with no gain, from the threat of the hex the
   unit is in, and takes the best of the stand and the steps. So a unit that is not pressed
   pulls back out of the line of sight and waits there, and comes out on the turn the
   schedule names. The defender that outranges the attacker gets no free turns of fire.

7. The threat counts the machine guns. Agent v4 reads the inherent firepower of each enemy
   unit and not the weapon it carries, so a squad with a heavy machine gun reads as four
   firepower to six hexes when it is ten firepower to sixteen. Agent v6 adds each weapon an
   enemy carries, at the range of the weapon (rules 9.2 and 17.1).

8. The defender holds what the attacker wants. Agent v1 gives each side the set up areas
   of the enemy groups the scenario marks, so the German defender of scenario 1 walks
   toward the Russian buildings. In v6 a side with no deadline reads the positional
   conditions of the other side and holds the places they name: its own buildings in a
   swing, the factory in a hex count. Its units stand in them and fire.

9. The plan. Agent v1 measures the distance to the nearest objective hex, and each
   objective hex stays an objective for the whole game. So the whole force walks to the
   nearest building, takes it, and stands in it while the other four wait. Agent v6 makes a
   plan at each decision. It drops each building it controls, selects the nearest open
   buildings it needs (the margin of the swing plus one, or all of them for a hex count),
   and divides the force among them by distance, with an equal share for each. A unit
   measures its gain to its own building. One squad stays in each taken building as its
   garrison, so the building does not change hands behind the advance. A building of its
   own that the swing names and that stands empty with an enemy near it, or that the enemy
   took, gets one unit back, because a building lost cancels a building taken. The plan is a
   pure function of the state, so a replay gives the same plan (TR-02).

The nation profiles carry the v5 biases. The Soviet profile presses first, because Soviet
doctrine accepted losses to keep the timetable. The American profile presses last, because
American doctrine leaned on fire and took its time.

What v6 does not do: it has no policy for a vehicle, so on an armor board its tanks stand,
and the tanker v3 drives them. It measures one step at a time, so it does not plan a
whole turn of movement. On scenario 1 it wins as the Russian attacker against a random
German in 28 of 30 games, where v5 won none, and it loses to a v1 or v5 German in most
games, because the German outranges the Russian and the streets are open. That is the
next measurement to change.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, replace

from slcore import geometry
from slcore.engine import Engine
from slcore.frame import DecisionFrame, LegalCommand
from slcore.game import PHASE_PREP_FIRE, State
from slcore.geometry import HexRef
from slcore.rules.r13_rout import is_cover
from slcore.los_eval import evaluate as evaluate_los
from slcore.rules import r05_movement, r06_stacking, r08_fire, victory
from slcore.rules.victory import (
    KIND_BUILDING_COUNT,
    KIND_BUILDING_SWING,
    KIND_HEX_CONTROL,
    KIND_SOLE_OCCUPANT,
)
from slcore.units import KIND_LEADER, KIND_SW, Unit

from slagents.scripted.v5 import Parameters as V5Parameters
from slagents.scripted.v5 import ScriptedV5

# A victory condition of one of these kinds names a place, so the side that holds it has a
# deadline: it must be there when the last turn ends.
POSITIONAL_KINDS = (KIND_BUILDING_SWING, KIND_BUILDING_COUNT, KIND_HEX_CONTROL, KIND_SOLE_OCCUPANT)

# An enemy this close to an empty building of ours is a threat to it, so one unit goes back.
HOLD_RADIUS = 3

# Rule 16.5: fire at a unit that moves in open ground gets a minus two, so the threat of an
# open hex counts double.
OPEN_GROUND_FACTOR = 2

# A hex with an unbroken enemy in it is not a step of a route, unless it is the target. The
# route goes around it at this cost in movement halves.
ENEMY_HEX_HALVES = 20


@dataclass(frozen=True)
class Parameters:
    """The named parameters of v6. It is a superset of the v5 parameters (FR-44)."""

    aggression: int = 2
    cover_preference: int = 3
    fire_priority: int = 2
    group_size: int = 3
    advance_into_close_combat: bool = True
    threat_aversion: int = 1
    close_combat_superiority: int = 2
    superiority_tenths: int = 15
    suppression_priority: int = 2
    # v6 adds these:
    threat_scale: int = 8  # firepower halves for one unit of threat: one squad of four
    schedule_margin: int = 2  # turns of slack below which a unit is pressed to move
    route_risk: int = 2  # movement halves that one unit of threat adds to a hex on the route


NATION_PROFILES: dict[str, Parameters] = {
    "german": Parameters(aggression=3, cover_preference=3, fire_priority=2, threat_aversion=1, superiority_tenths=13, suppression_priority=2, schedule_margin=2),
    "soviet": Parameters(aggression=3, cover_preference=2, fire_priority=2, threat_aversion=1, close_combat_superiority=2, superiority_tenths=12, suppression_priority=1, schedule_margin=3),
    "american": Parameters(aggression=2, cover_preference=4, fire_priority=3, threat_aversion=2, superiority_tenths=18, suppression_priority=3, schedule_margin=1),
}


class UnknownNation(Exception):
    """The nation profile is not defined. British waits for its research pass."""


def profile_for(nation: str) -> Parameters:
    key = nation.strip().lower()
    if key not in NATION_PROFILES:
        raise UnknownNation(
            f"no v6 profile for {nation!r}. Defined: {', '.join(sorted(NATION_PROFILES))}. "
            f"British is not confirmed yet and waits for a follow-up research pass."
        )
    return NATION_PROFILES[key]


def with_parameters(**changes: object) -> Parameters:
    return replace(Parameters(), **changes)


class ScriptedV6(ScriptedV5):
    name = "scripted"
    version = "6"

    def __init__(self, engine: Engine, player: int, params: Parameters | None = None) -> None:
        self.v6 = params or Parameters()
        super().__init__(
            engine,
            player,
            V5Parameters(
                aggression=self.v6.aggression,
                cover_preference=self.v6.cover_preference,
                fire_priority=self.v6.fire_priority,
                group_size=self.v6.group_size,
                advance_into_close_combat=self.v6.advance_into_close_combat,
                threat_aversion=self.v6.threat_aversion,
                close_combat_superiority=self.v6.close_combat_superiority,
                superiority_tenths=self.v6.superiority_tenths,
                suppression_priority=self.v6.suppression_priority,
            ),
        )
        self.has_deadline = self._side_has_deadline()
        self.targets_wanted = self._targets_wanted()
        self.own_places = self._own_places()
        if not self.has_deadline:
            held = self._places_to_defend()
            if held:
                self.objectives = held
        # The objective hexes this side does not hold yet, and the hexes each unit measures
        # its gain to. Both are set at each decision from the state.
        self.open_objectives: tuple[HexRef, ...] = self.objectives
        self.assignment: dict[int, tuple[HexRef, ...]] = {}
        # The unit that holds each own building in danger. It keeps the task until it is
        # broken or gone, so the task does not pass from unit to unit as the force moves.
        self.holders: dict[str, int] = {}
        # The route fields of this enemy picture, one for each target, and the threat map.
        self._picture: tuple = ()
        self._threat_map: dict[HexRef, int] = {}
        self._fields: dict[tuple[tuple[HexRef, ...], bool], dict[HexRef, int]] = {}

    # ---------------------------------------------------------- the objectives

    def select(self, state: State, frame: DecisionFrame) -> str:
        self._refresh_routes(state)
        self._refresh_objectives(state)
        return super().select(state, frame)

    def _targets_wanted(self) -> int:
        """How many objective places the side must take: the swing margin plus one.

        A building the other side takes back cancels one that this side took, so the plan
        aims one building past the margin. A hex count or a sole occupant condition names one
        place, so every open place is a target. Zero means every open place.
        """
        side = self.engine.scenario.players()[self.player]
        for condition in self.engine.scenario.victory:
            params = dict(condition.params)
            if condition.kind == KIND_BUILDING_SWING and str(params.get("side", "")) == side:
                return int(params.get("margin", 1)) + 1
        return 0

    def _places_to_defend(self) -> tuple[HexRef, ...]:
        """The hexes the other side's positional conditions name, for a side with no deadline."""
        scenario = self.engine.scenario
        other = scenario.players()[self.opponent]
        out: list[HexRef] = []
        for condition in scenario.victory:
            params = dict(condition.params)
            if condition.kind not in POSITIONAL_KINDS or str(params.get("side", "")) != other:
                continue
            groups = list(params.get("enemy_groups", [])) + list(params.get("groups", []))
            out.extend(victory.group_hexes(scenario, self.engine.board, groups))
        return tuple(sorted(set(out)))

    def _own_places(self) -> list[tuple[str, tuple[HexRef, ...]]]:
        """The buildings of this side that a swing condition counts as lost when the enemy takes them."""
        side = self.engine.scenario.players()[self.player]
        by_building = victory.buildings_on(self.engine.board)
        out: list[tuple[str, tuple[HexRef, ...]]] = []
        for condition in self.engine.scenario.victory:
            params = dict(condition.params)
            if condition.kind != KIND_BUILDING_SWING or str(params.get("side", "")) != side:
                continue
            for building_id in victory.group_buildings(self.engine.scenario, self.engine.board, params.get("own_groups", [])):
                if building_id in by_building and (building_id, by_building[building_id]) not in out:
                    out.append((building_id, by_building[building_id]))
        return out

    def _places_to_hold(self, state: State, units: list[Unit]) -> list[tuple[str, tuple[HexRef, ...]]]:
        """The own buildings that need a unit: taken by the enemy, or empty with an enemy near.

        Near is within `HOLD_RADIUS` hexes. A building with an unbroken unit of this side
        inside it needs nothing more.
        """
        out: list[tuple[str, tuple[HexRef, ...]]] = []
        enemies = [u.hex for u in state.player_units(self.opponent) if u.hex is not None and u.is_infantry and not u.broken]
        for place_id, hexes in self.own_places:
            if any(u.hex in hexes and not u.broken for u in units):
                continue
            if not victory.controlled_by(state, self.engine.board, place_id, self.player):
                out.append((place_id, hexes))
                continue
            if any(geometry.distance(e, h) <= HOLD_RADIUS for e in enemies for h in hexes):
                out.append((place_id, hexes))
        return out

    def _places(self) -> list[tuple[str, tuple[HexRef, ...]]]:
        """The objective places: each building with an objective hex, and each loose hex."""
        by_building = victory.buildings_on(self.engine.board)
        places: list[tuple[str, tuple[HexRef, ...]]] = []
        loose: list[HexRef] = []
        seen: set[HexRef] = set()
        for building_id, hexes in sorted(by_building.items()):
            if any(h in self.objectives for h in hexes):
                places.append((building_id, hexes))
                seen.update(hexes)
        for h in self.objectives:
            if h not in seen:
                loose.append(h)
        for h in loose:
            places.append((geometry.hex_id(*h), (h,)))
        return places

    def _refresh_objectives(self, state: State) -> None:
        """The plan of this decision: the open places, the targets, and the unit shares.

        A place is taken when this side controls it (rule of the scenario card, through the
        core's evaluator). A taken place keeps one garrison: the unbroken squad of the lowest
        id inside it. The other units divide among the nearest open targets, an equal share
        for each target, closest unit first. A unit measures its gain to its own target.
        """
        board = self.engine.board
        taken: list[tuple[str, tuple[HexRef, ...]]] = []
        open_places: list[tuple[str, tuple[HexRef, ...]]] = []
        for place_id, hexes in self._places():
            if len(hexes) == 1 and board.hex(hexes[0]).building is None:
                held = victory.hex_controlled_by(state, hexes[0], self.player)
            else:
                held = victory.controlled_by(state, board, place_id, self.player)
            (taken if held else open_places).append((place_id, hexes))
        open_hexes = tuple(h for _, hexes in open_places for h in hexes)
        self.open_objectives = open_hexes if open_hexes else self.objectives

        units = [
            u
            for u in state.player_units(self.player)
            if u.hex is not None and u.is_infantry and not u.eliminated and u.carrier is None
        ]
        assignment: dict[int, tuple[HexRef, ...]] = {}
        for _, hexes in taken:
            inside = [u for u in units if u.hex in hexes and not u.broken and u.kind != KIND_LEADER]
            if inside:
                assignment[min(u.id for u in inside)] = hexes
        free = [u for u in units if u.id not in assignment]
        # One unit goes back to each own building that stands in danger: the one that holds
        # the task, or else the nearest one.
        to_hold = self._places_to_hold(state, units)
        self.holders = {pid: uid for pid, uid in self.holders.items() if pid in {p for p, _ in to_hold}}
        for place_id, hexes in to_hold:
            candidates = [u for u in free if not u.broken and u.kind != KIND_LEADER]
            if not candidates:
                break
            kept = [u for u in candidates if u.id == self.holders.get(place_id)]
            chosen = kept[0] if kept else min(candidates, key=lambda u: (min(geometry.distance(u.hex, h) for h in hexes), u.id))
            self.holders[place_id] = chosen.id
            assignment[chosen.id] = hexes
            free = [u for u in free if u.id != chosen.id]
        if not open_places or not free:
            self.assignment = assignment
            return

        wanted = self.targets_wanted if self.targets_wanted > 0 else len(open_places)
        targets = self._target_order(state, free, open_places)[: max(1, min(wanted, len(open_places)))]
        share = (len(free) + len(targets) - 1) // len(targets)
        room = {place_id: share for place_id, _ in targets}

        def nearest(u: Unit) -> tuple[int, int]:
            return (min(geometry.distance(u.hex, h) for _, hexes in targets for h in hexes), u.id)

        for u in sorted(free, key=nearest):
            options = [
                (min(geometry.distance(u.hex, h) for h in hexes), place_id, hexes)
                for place_id, hexes in targets
                if room[place_id] > 0
            ]
            if not options:
                options = [(min(geometry.distance(u.hex, h) for h in hexes), place_id, hexes) for place_id, hexes in targets]
            _, place_id, hexes = min(options)
            room[place_id] -= 1
            assignment[u.id] = hexes
        self.assignment = assignment

    def _target_order(
        self, state: State, free: list[Unit], open_places: list[tuple[str, tuple[HexRef, ...]]]
    ) -> list[tuple[str, tuple[HexRef, ...]]]:
        """The open places in the order the plan takes them: the nearest to the force first."""

        def force_distance(place: tuple[str, tuple[HexRef, ...]]) -> tuple[int, str]:
            total = sum(min(geometry.distance(u.hex, h) for h in place[1]) for u in free)
            return (total, place[0])

        return sorted(open_places, key=force_distance)

    # ---------------------------------------------------------------- the threat

    def _threat(self, state: State, dst: HexRef, cache: dict[HexRef, int]) -> int:
        """v5's threat, plus the weapon each unbroken enemy infantry unit carries."""
        found = cache.get(dst)
        if found is not None:
            return found
        total = super()._threat(state, dst, cache)
        for enemy in state.player_units(self.opponent):
            if enemy.hex is None or enemy.broken or enemy.is_vehicle:
                continue
            for weapon in state.carried_by(enemy.id):
                if weapon.kind != KIND_SW or weapon.broken:
                    continue
                fire = r08_fire.member_firepower(state, self.engine.types, enemy, weapon, dst, False)
                if fire is None:
                    continue
                if evaluate_los(self.engine.board, self.engine.los, enemy.hex, dst).clear:
                    total += fire.halves
        cache[dst] = total
        return total

    # ---------------------------------------------------------------- the route

    def _enemy_picture(self, state: State) -> tuple:
        """What the route depends on: the turn, the phase, and each unbroken enemy position."""
        enemies = tuple(sorted((u.hex, u.type_key) for u in state.player_units(self.opponent) if u.hex is not None and not u.broken))
        return (state.turn, state.phase, state.active, enemies)

    def _refresh_routes(self, state: State) -> None:
        picture = self._enemy_picture(state)
        if picture == self._picture:
            return
        self._picture = picture
        self._threat_map = {}
        self._fields = {}

    def _hex_risk(self, state: State, hex_ref: HexRef) -> int:
        """The threat of a hex in movement halves, for the route cost."""
        threat = self._threat(state, hex_ref, self._threat_map) // max(1, self.v6.threat_scale)
        threat = threat // 2 if is_cover(self.engine.board, hex_ref) else threat * OPEN_GROUND_FACTOR
        return threat * self.v6.route_risk

    def _route_field(self, state: State, target: tuple[HexRef, ...], safe: bool = True) -> dict[HexRef, int]:
        """The least cost from each hex to the target, in movement halves plus risk.

        A search from the target outward. The cost of a step from h into k is the entry
        cost of rule 5.5 plus the risk of k. A hexside that no unit can cross has no step.
        A hex with an unbroken enemy costs `ENEMY_HEX_HALVES` more, and a target hex costs
        nothing, so the route ends in the target and goes around the other enemy hexes.
        With safe off the risk is out of the cost, and the field is the fastest route.
        """
        found = self._fields.get((target, safe))
        if found is not None:
            return found
        board = self.engine.board
        ctx = self.engine.move_ctx
        enemy_hexes = {u.hex for u in state.player_units(self.opponent) if u.hex is not None and not u.broken and u.is_infantry}
        targets = set(target)
        dist: dict[HexRef, int] = {}
        heap: list[tuple[int, HexRef]] = [(0, t) for t in target if t in board]
        heapq.heapify(heap)
        while heap:
            d, k = heapq.heappop(heap)
            if k in dist:
                continue
            dist[k] = d
            if k in targets:
                enter_k = 0
            else:
                enter_k = (self._hex_risk(state, k) if safe else 0) + (ENEMY_HEX_HALVES if k in enemy_hexes else 0)
            for h in board.neighbors(k):
                if h in dist:
                    continue
                cost, _ = r05_movement.entry_cost_halves(ctx, h, k)
                if cost is None:
                    continue
                heapq.heappush(heap, (d + cost + enter_k, h))
        self._fields[(target, safe)] = dist
        return dist

    def _route_cost(self, state: State, target: tuple[HexRef, ...], hex_ref: HexRef, safe: bool = True) -> int:
        if not target:
            # No place to go: every objective is taken, or the side has none. Each hex is
            # as good as the next, so a step gains nothing on the route.
            return 0
        field = self._route_field(state, target, safe)
        found = field.get(hex_ref)
        if found is None:
            # No route: the hex distance in halves of open ground, so a cut-off unit still
            # leans toward the target.
            return 2 * min(geometry.distance(hex_ref, o) for o in target) + 1000
        return found

    def _distance(self, hex_ref: HexRef) -> int:
        if not self.open_objectives:
            return 0
        return min(geometry.distance(hex_ref, o) for o in self.open_objectives)

    def _unit_distance(self, unit_id: int, hex_ref: HexRef) -> int:
        """The distance for one unit: to its own target, or to the nearest open place."""
        own = self.assignment.get(unit_id)
        if own is not None:
            return min(geometry.distance(hex_ref, o) for o in own)
        return self._distance(hex_ref)

    # ------------------------------------------------------------- the schedule

    def _side_has_deadline(self) -> bool:
        """True when a victory condition of this side names a place to hold at game end."""
        side = self.engine.scenario.players()[self.player]
        for condition in self.engine.scenario.victory:
            params = dict(condition.params)
            if condition.kind in POSITIONAL_KINDS and str(params.get("side", "")) == side:
                return True
        return False

    def _turns_left(self, state: State) -> int:
        """This turn and each turn after it. The turn count is 1-based."""
        return max(0, self.engine.scenario.turns - state.turn + 1)

    def _slack(self, state: State, unit_id: int, unit_hex: HexRef) -> int:
        """Turns of slack: the turns left, minus the turns the fastest route needs.

        The route is in movement halves. A turn gives the unit its allowance in the
        Movement Phase and one hex in the Advance Phase, which counts as two halves.
        """
        target = self.assignment.get(unit_id, self.open_objectives)
        cost = self._route_cost(state, target, unit_hex, safe=False)
        if cost >= 1000:
            cost = 2 * self._unit_distance(unit_id, unit_hex)
        per_turn = max(2, self.engine.types[state.units[unit_id].type_key].mf_halves + 2)
        needed = (cost + per_turn - 1) // per_turn
        return self._turns_left(state) - needed

    def _pressed(self, state: State, unit_id: int, unit_hex: HexRef) -> bool:
        if not self.has_deadline or self._unit_distance(unit_id, unit_hex) == 0:
            return False
        return self._slack(state, unit_id, unit_hex) < self.v6.schedule_margin

    # ----------------------------------------------------------- the step score

    def _step_score(self, state: State, unit_id: int, unit_hex: HexRef, dst: HexRef, cache: dict[HexRef, int], bonus: int = 0, count: int = 1, moving: bool = True) -> tuple[int, int]:
        """The score of one step from unit_hex to dst: (pressed gain, value).

        The threat is in squads. Cover halves it. A step in the Movement Phase in open
        ground doubles it (rule 16.5) and the size of the stack multiplies it. A step in
        the Advance Phase draws no defensive fire (rule 4, the phase sequence), so its threat
        is the fire of the next enemy turn on a stationary unit: no doubling and no stack
        factor. When the unit is pressed, the first element is 1 for a step with a gain
        toward the objective and 0 for the others, so a step with a gain beats a stand and
        the value orders the steps with a gain. When the unit is not pressed the first
        element is 0 and the value alone decides, as in v5.
        """
        target = self.assignment.get(unit_id, self.open_objectives)
        is_pressed = self._pressed(state, unit_id, unit_hex)
        safe = not is_pressed
        gain = self._route_cost(state, target, unit_hex, safe) - self._route_cost(state, target, dst, safe)
        covered = is_cover(self.engine.board, dst)
        cover = self.v6.cover_preference if covered else 0
        threat = self._threat(state, dst, cache) // max(1, self.v6.threat_scale)
        if covered:
            threat //= 2
        elif moving:
            threat *= OPEN_GROUND_FACTOR
        if moving:
            threat *= max(1, count)
        value = gain * self.v6.aggression + cover + bonus - threat * self.v6.threat_aversion
        pressed = 1 if gain > 0 and is_pressed else 0
        return (pressed, value)

    # ------------------------------------------------------------------ fire

    def _fire(self, state: State, frame: DecisionFrame, by_action: dict[str, list[LegalCommand]]) -> str:
        """v5's fire, with the pressed units kept out of the Prep Fire Phase (rule 8.1)."""
        if frame.phase == PHASE_PREP_FIRE and self.has_deadline:
            kept: dict[str, list[LegalCommand]] = {}
            for action, commands in by_action.items():
                if action in ("group_add", "group_add_weapon"):
                    commands = [lc for lc in commands if not self._maneuver_unit(state, lc.command.units[0])]
                    if not commands:
                        continue
                kept[action] = commands
            by_action = kept
        return super()._fire(state, frame, by_action)

    def _maneuver_unit(self, state: State, unit_id: int) -> bool:
        unit = state.units[unit_id]
        if unit.hex is None:
            return False
        return self._pressed(state, unit_id, unit.hex)

    def _stand_value(self, state: State, unit_id: int, cache: dict[HexRef, int]) -> int:
        """The value of a stand in the hex the unit is in: no gain, its cover, its threat.

        Rule 16.5 gives the minus two to a unit that moves in the open, so the threat of
        the stand does not double. The stack is what stands in the hex now.
        """
        unit = state.units[unit_id]
        if unit.hex is None:
            return 0
        covered = is_cover(self.engine.board, unit.hex)
        cover = self.v6.cover_preference if covered else 0
        threat = self._threat(state, unit.hex, cache) // max(1, self.v6.threat_scale)
        if covered:
            threat //= 2
        count = sum(1 for u in state.infantry_in(unit.hex) if u.player == self.player and not u.broken)
        threat *= max(1, count)
        return cover - threat * self.v6.threat_aversion

    # -------------------------------------------------------------- movement

    def _move(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        cache: dict[HexRef, int] = {}
        best: LegalCommand | None = None
        best_score: tuple[int, int, int] | None = None
        stand: dict[int, int] = {}
        for action in ("stack_move", "move"):
            for lc in by_action.get(action, []):
                unit = state.units[lc.command.units[0]]
                dst = lc.command.hex
                if unit.hex is None or dst is None:
                    continue
                if self._would_overstack(state, dst, lc.command.units):
                    continue
                pressed, value = self._step_score(state, unit.id, unit.hex, dst, cache, count=len(lc.command.units))
                if unit.id not in stand:
                    stand[unit.id] = self._stand_value(state, unit.id, cache)
                # A step is worth taking when it beats the stand.
                score = (pressed, value - stand[unit.id], len(lc.command.units))
                if best_score is None or score > best_score or (score == best_score and best is not None and lc.id < best.id):
                    best = lc
                    best_score = score
        if best is not None and best_score is not None and (best_score[0] > 0 or best_score[1] > 0):
            return best.id
        if "end_phase" in by_action:
            return by_action["end_phase"][0].id
        return self._relief(state, by_action, best)

    def _would_overstack(self, state: State, dst: HexRef, units: tuple[int, ...]) -> bool:
        return r06_stacking.rule_6_1_overstacked(state, self.engine.types, dst, self.player, extra_ids=tuple(units))

    def _relief(self, state: State, by_action: dict[str, list[LegalCommand]], best: LegalCommand | None) -> str:
        """Rule 6.3: a unit must leave a hex over the limit. Take the safest step out."""
        over = set(r06_stacking.overstacked_hexes(state, self.engine.types, self.player))
        moves = by_action.get("stack_move", []) + by_action.get("move", []) + by_action.get("sewer_move", [])
        out_of_the_hex = [lc for lc in moves if any(state.units[uid].hex in over for uid in lc.command.units)]
        if not out_of_the_hex:
            return super()._relief(state, by_action, best)
        cache: dict[HexRef, int] = {}

        def order(lc: LegalCommand) -> tuple[int, int, int, str]:
            unit = state.units[lc.command.units[0]]
            dst = lc.command.hex
            if unit.hex is None or dst is None:
                return (1, 0, 0, lc.id)
            fits = 0 if self._would_overstack(state, dst, lc.command.units) else -1
            _, value = self._step_score(state, unit.id, unit.hex, dst, cache, count=len(lc.command.units))
            return (fits, -value, -len(lc.command.units), lc.id)

        return min(out_of_the_hex, key=order).id

    # --------------------------------------------------------------- advance

    def _advance(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        """The v4 assault gate, on the v6 step score.

        An advance into a hex with an unbroken enemy is a close combat. It is a reason to
        advance only when the enemy there is broken or when the stack brings local
        superiority (v4). A pressed unit still keeps that gate: the schedule does not send a
        squad alone into a fresh defender.
        """
        cache: dict[HexRef, int] = {}
        best: LegalCommand | None = None
        best_score: tuple[int, int, int, int] | None = None
        for lc in by_action.get("advance", []):
            unit = state.units[lc.command.units[0]]
            dst = lc.command.hex
            if unit.hex is None or dst is None:
                continue
            if self._would_overstack(state, dst, lc.command.units):
                continue
            enemies = [u for u in state.infantry_in(dst) if u.player != self.player]
            unbroken = [u for u in enemies if not u.broken]
            favorable = self._assault_is_favorable(len(lc.command.units), unbroken)
            if unbroken and not favorable:
                if not self.v6.advance_into_close_combat:
                    continue
                bonus = 0
            else:
                bonus = len(enemies) * self.v6.aggression
            pressed, value = self._step_score(state, unit.id, unit.hex, dst, cache, bonus, len(lc.command.units), moving=False)
            if unbroken and not favorable:
                pressed = 0  # the schedule does not override the assault gate
            score = (pressed, value, 1 if (not unbroken or favorable) else 0, -len(unbroken))
            if best_score is None or score > best_score or (score == best_score and best is not None and lc.id < best.id):
                best = lc
                best_score = score
        if best is not None and best_score is not None and (best_score[0] > 0 or best_score[1] > 0):
            return best.id
        return self._first_of(by_action, ("end_phase",))
