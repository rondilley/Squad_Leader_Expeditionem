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

The combined-arms pass (2026-10-11). The owner watched v7 and v6 on scenario 4 and said:
"The tanks do not appear to be working in coordination or within written doctrines for tank
warfare, small unit tactics, mixed unit tactics." A measure of 20 games agreed: a tank had a
squad of its own in or next to its hex in 0 to 13 percent of the samples, and the Allied
tanks of v6 lost 20 of 30. Each tank chose its hex and its target alone. The pass puts the
principles of RV-9 into the policy:

- P13, tanks and infantry cover each other. A firing position more than `leash` hexes from
  the own infantry costs `leash_cost` halves for each hex past it, so the tanks stay with
  the force. A tank with an own squad or crew in or next to its hex is screened, so it may
  stand `escorted_standoff` hexes from enemy infantry in place of `standoff`. A route hex in
  the anti-tank range of enemy infantry with no escort costs `danger_cost` halves. The
  infantry half of the team is in v6 and v7 (`escort_bonus`): a squad of the attacker gains
  for a step next to a tank of its own that is near the enemy and has no escort yet.
- P7, bounding overwatch. In contact (an enemy within `contact_range` of the tank), a tank
  leaves its hex only while another tank of its own holds a firing position, and it ends
  each step within `overwatch_range` of that tank. With no tank in a firing position, the
  section bounds by halves: one half moves in an odd turn, the other in an even turn. A
  tank that will move does not fire in the Prep Fire Phase, because rule 33.2 holds a tank
  that fired there.
- P6, fire as a section. A shot gets `focus_bonus` for a hex that a tank of its own already
  fired at in this phase and that still holds an unbroken enemy, `threat_bonus` for a hex
  with an enemy anti-tank weapon, and `support_bonus` for a hex within three hexes of the
  own infantry, the enemy that stops the infantry.
- P4, flank and front. A firing position that sees an enemy vehicle's side or rear (rule
  33.5) costs `flank_bonus` halves less, and one in the sight and range of each enemy gun
  costs `gun_exposure` halves more. A tank that holds turns its front to the largest
  threat: an enemy gun first, then an enemy anti-tank weapon, then the nearest enemy.
- A tank in a firing position holds there unless another position is `hold_margin` halves
  better by the route, so a tank does not leave a good position for a small gain.

The base of fire (2026-10-14, `base_of_fire`, off by default). In scenario 4 the Russian
infantry sets up below concealment counters, and the policy saw only the units it can see.
So no hex was a firing position, each tank drove towards the objective, and it fired in the
Advancing Fire Phase after its move, with the case F penalty of rule 33.3 (plus 5 in the
trace of 2026-10-14). With `base_of_fire`, each enemy counter that covers no unit the
player sees is an enemy infantry position: a target that makes a hex a firing position, a
hex the standoff keeps away from, and a target of one unit for a shot. A tank thus stops in a
firing position and holds, and a tank that holds fires in the Prep Fire Phase, before the
infantry moves (rule 33.2 keeps it there). Rule 25.2 makes the counter public, and the policy
does not read what is below it.

The policy reads the state and the frame and picks one legal command, or None so that the
infantry policy of the agent decides. It keeps one record between decisions: the hexes its
tanks fired at in the phase in hand, for the section fire.
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
from slcore.units import KIND_CREW, KIND_SQUAD

ARMOR_FIRE_ACTIONS = ("at_fire", "afv_fire", "afv_mg", "afv_attack")
UNREACHABLE = 10**9
# The extra cost, in movement halves, of a hex that needs the breakdown die of rule 39.1,
# for each face of the die that breaks the vehicle there: a German vehicle breaks on a 5 or
# a 6 (two faces, 24 halves, two turns of a tank's movement), another army's on a 6 (12).
# An assault gun of the first version of this policy drove into a wood on its first turn
# and stood for the rest of the game. A tank goes around rough ground unless the way around
# is much longer.
BREAKDOWN_PENALTY = 12
# The units that screen a tank (P13): a squad or a crew on foot. A leader alone does not.
ESCORT_KINDS = (KIND_SQUAD, KIND_CREW)
# An enemy this near an own unbroken squad is the enemy that stops the infantry (P6).
SUPPORT_RADIUS = 3


@dataclass(frozen=True)
class ArmorParameters:
    """The named parameters of the armor policy (FR-44)."""

    armor_priority: int = 6  # what a shot at a vehicle adds over a shot at infantry
    fire_priority: int = 2  # the weight of each unbroken unit in a target hex
    standoff: int = 4  # hexes a tank keeps from enemy infantry (panzerfaust 3, bazooka 4)
    fire_range: int = 12  # the farthest target that makes a hex a firing position
    overrun: bool = True  # whether a tank drives over weak infantry (rule 35)
    pivot_to_aim: bool = True  # whether a tank that holds turns to face its target
    # The combined-arms pass (2026-10-11).
    escort: bool = True  # P13: the tanks stay with the infantry, and a screened tank may close in
    leash: int = 3  # hexes from the own infantry that a firing position may be at no cost
    leash_cost: int = 4  # movement halves for each hex past the leash
    escorted_standoff: int = 2  # hexes a screened tank keeps from enemy infantry
    danger_cost: int = 8  # movement halves of a route hex in the AT range of enemy infantry, with no escort
    bound: bool = True  # P7: bounding overwatch in contact
    contact_range: int = 12  # hexes: an enemy this near a tank puts it in contact
    overwatch_range: int = 8  # hexes a bounding tank may be from the tank that watches it
    section_fire: bool = True  # P6: the tanks fire as a section
    focus_bonus: int = 4  # a hex that a tank of ours fired at in this phase
    threat_bonus: int = 3  # a hex with an enemy anti-tank weapon
    support_bonus: int = 3  # a hex near the own infantry
    flank_bonus: int = 8  # movement halves off a position that sees an enemy side or rear
    gun_exposure: int = 6  # movement halves on a position for each enemy gun that sees it
    hold_margin: int = 4  # movement halves another position must gain before a tank leaves its own
    base_of_fire: bool = False  # an enemy counter with no unit this player sees is an enemy infantry position


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
        self._costs: dict[tuple, dict[HexRef, int]] = {}
        self._danger: dict[tuple, dict[HexRef, int]] = {}
        # The hexes the tanks of this side fired at in the phase in hand (P6). The key is
        # the turn and the phase; each phase of an agent comes one time in a turn.
        self._shots_key: tuple[int, str] = (-1, "")
        self._shots: set[HexRef] = set()

    # ------------------------------------------------------------------ choose

    def choose(self, state: State, frame: DecisionFrame, by_action: dict[str, list[LegalCommand]]) -> str | None:
        phase = frame.phase
        if phase == PHASE_RALLY and "afv_repair" in by_action:
            # Rule 38.1: a gun that nobody works on stays broken for the game.
            return min(by_action["afv_repair"], key=lambda lc: lc.id).id
        if phase in (PHASE_PREP_FIRE, PHASE_DEFENSIVE_FIRE, PHASE_ADVANCING_FIRE):
            if phase == PHASE_PREP_FIRE:
                by_action = self._without_movers(state, by_action)
            shot = self._armor_shot(state, by_action)
            if shot is not None:
                self._record_shot(state, shot)
                return shot.id
            if phase in (PHASE_PREP_FIRE, PHASE_DEFENSIVE_FIRE):
                return self._aim(state, by_action)
        if phase == PHASE_MOVEMENT:
            return self._drive(state, by_action)
        if phase == PHASE_CLOSE_COMBAT and "cc_afv" in by_action:
            # Rule 36.23: a squad that stands on a tank kills it on its firepower factor.
            return min(by_action["cc_afv"], key=lambda lc: lc.id).id
        return None

    # -------------------------------------------------------------------- fire

    def _armor_shot(self, state: State, by_action: dict[str, list[LegalCommand]]) -> LegalCommand | None:
        best: LegalCommand | None = None
        best_score: tuple[int, int] | None = None
        for action in ARMOR_FIRE_ACTIONS:
            for lc in by_action.get(action, []):
                score = self._shot_score(state, action, lc)
                if score is None:
                    continue
                if best_score is None or score > best_score or (score == best_score and best is not None and lc.id < best.id):
                    best, best_score = lc, score
        return best

    def _shot_score(self, state: State, action: str, lc: LegalCommand) -> tuple[int, int] | None:
        target = lc.command.hex
        if target is None:
            return None
        payload = dict(lc.command.extra)
        vehicle = r28_vehicles.vehicle_in(state, target)
        hostile = vehicle is not None and vehicle.player != self.player and not vehicle.wreck
        occupants = [u for u in state.infantry_in(target) if u.player != self.player and not u.broken]
        if not occupants and target in self._enemy_counters(state):
            # The base of fire: the counter is worth one unit, the stand-in of the threat
            # model, at the firepower that rule 25.8 halves.
            occupants = [None]
        focus = self._focus(state, target)
        if action == "at_fire":
            # Rule 37: the weapon has no other target, so it fires when it can.
            return (self.params.armor_priority * 2 + focus, 0) if hostile else None
        if action == "afv_attack":
            return (self.params.armor_priority + focus, 0) if hostile else None
        if action == "afv_fire":
            if str(payload.get("aim")) == "vehicle":
                return (self.params.armor_priority + focus, 0) if hostile else None
            if not occupants:
                return None
            return (self.params.fire_priority * len(occupants) + self._section_value(state, target, occupants) + focus, len(occupants))
        if action == "afv_mg":
            if not occupants:
                return None
            return (self.params.fire_priority * len(occupants) - 1 + self._section_value(state, target, occupants) + focus, len(occupants))
        return None

    def _section_value(self, state: State, target: HexRef, occupants: list) -> int:
        """P6: what the hex is worth to the force: an enemy anti-tank weapon, and an enemy
        near the own infantry."""
        if not self.params.section_fire:
            return 0
        value = 0
        types = self.engine.types
        if any(u is not None and r37_at_weapons.anti_tank_weapons(state, types, u) for u in occupants):
            value += self.params.threat_bonus
        if any(geometry.distance(target, f) <= SUPPORT_RADIUS for f in self._friends(state)):
            value += self.params.support_bonus
        return value

    def _focus(self, state: State, target: HexRef) -> int:
        if not self.params.section_fire:
            return 0
        if self._shots_key != (state.turn, state.phase):
            return 0
        return self.params.focus_bonus if target in self._shots else 0

    def _record_shot(self, state: State, shot: LegalCommand) -> None:
        key = (state.turn, state.phase)
        if self._shots_key != key:
            self._shots_key, self._shots = key, set()
        if shot.command.hex is not None:
            self._shots.add(shot.command.hex)

    def _without_movers(self, state: State, by_action: dict[str, list[LegalCommand]]) -> dict[str, list[LegalCommand]]:
        """P7 with rule 33.2: a tank that fires in the Prep Fire Phase may not move, so a tank
        that will bound in this player turn keeps its fire for the Advancing Fire Phase."""
        movers = self._movers(state)
        if not movers:
            return by_action
        out: dict[str, list[LegalCommand]] = {}
        for action, commands in by_action.items():
            if action in ARMOR_FIRE_ACTIONS:
                commands = [lc for lc in commands if not (lc.command.units and lc.command.units[0] in movers)]
                if not commands:
                    continue
            out[action] = commands
        return out

    # ---------------------------------------------------------------- the picture

    def _enemies(self, state: State) -> list:
        return [u for u in state.player_units(1 - self.player) if u.hex is not None and not u.eliminated and not u.hidden and not u.wreck]

    def _enemy_infantry(self, state: State) -> list[HexRef]:
        seen = {u.hex for u in self._enemies(state) if u.is_infantry and not u.riding}
        return sorted(seen | self._enemy_counters(state))

    def _enemy_counters(self, state: State) -> frozenset[HexRef]:
        """With `base_of_fire`, the hexes of the enemy concealment counters that cover no
        enemy unit this player sees. Without it, none."""
        if not self.params.base_of_fire:
            return frozenset()
        seen = {u.hex for u in self._enemies(state)}
        return frozenset(c.hex for c in state.concealment if c.player != self.player and c.hex is not None and c.hex not in seen)

    def _enemy_guns(self, state: State) -> list:
        """The enemy vehicles with a working main armament."""
        types = self.engine.types
        return [
            u for u in self._enemies(state)
            if u.is_vehicle and types[u.type_key].gun > 0 and not u.malfunction and not u.disabled
        ]

    def _friends(self, state: State) -> frozenset[HexRef]:
        """The hexes of the own unbroken squads and crews on foot: the infantry that screens a tank."""
        if not self.params.escort:
            return frozenset()
        return frozenset(
            u.hex for u in state.player_units(self.player)
            if u.hex is not None and u.kind in ESCORT_KINDS and not u.broken and not u.eliminated and not u.riding
        )

    @staticmethod
    def _escorted(friends: frozenset[HexRef], here: HexRef) -> bool:
        return any(geometry.distance(here, f) <= 1 for f in friends)

    def _picture(self, state: State) -> tuple:
        return (tuple(sorted((u.id, u.hex) for u in self._enemies(state))), tuple(sorted(self._enemy_counters(state))))

    def _key(self, state: State) -> tuple:
        """The enemy picture and the own infantry: the things a position and a route read."""
        return (self._picture(state), self._friends(state))

    def firing_positions(self, state: State) -> frozenset[HexRef]:
        """The hexes with a line of sight to an enemy within `fire_range` and at least
        `standoff` hexes from each enemy infantry unit (`escorted_standoff` for a hex that
        an own squad or crew screens)."""
        key = self._key(state)
        found = self._positions.get(key)
        if found is not None:
            return found
        engine = self.engine
        enemies = sorted({u.hex for u in self._enemies(state)} | self._enemy_counters(state))
        infantry = self._enemy_infantry(state)
        friends = key[1]
        out = set()
        for here in engine.board.order:
            near = min((geometry.distance(here, h) for h in infantry), default=UNREACHABLE)
            keep = self.params.standoff
            if friends and self._escorted(friends, here):
                keep = min(keep, self.params.escorted_standoff)
            if near < keep:
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

    def goal_costs(self, state: State) -> dict[HexRef, int]:
        """The start cost of each firing position, in movement halves (P13 and P4): the leash
        to the own infantry, the enemy guns that see it, less the flank bonus."""
        key = self._key(state)
        found = self._costs.get(key)
        if found is not None:
            return found
        engine = self.engine
        friends = key[1]
        guns = {u.id for u in self._enemy_guns(state)}
        vehicles = [u for u in self._enemies(state) if u.is_vehicle]
        out: dict[HexRef, int] = {}
        for here in sorted(self.firing_positions(state)):
            cost = 0
            if friends:
                near = min(geometry.distance(here, f) for f in friends)
                cost += self.params.leash_cost * max(0, near - self.params.leash)
            exposed = 0
            flank = False
            for enemy in vehicles:
                if geometry.distance(here, enemy.hex) > self.params.fire_range:
                    continue
                if not evaluate_los(engine.board, engine.los, here, enemy.hex).clear:
                    continue
                if enemy.id in guns:
                    exposed += 1
                if r28_vehicles.target_face(enemy, here, engine.types) in (r28_vehicles.SIDE, r28_vehicles.REAR):
                    flank = True
            cost += self.params.gun_exposure * exposed
            if flank:
                cost -= self.params.flank_bonus
            out[here] = max(0, cost)
        self._costs = {key: out}
        return out

    def _danger_map(self, state: State) -> dict[HexRef, int]:
        """The extra cost of each hex in the AT range of enemy infantry with no escort (P13)."""
        key = self._key(state)
        found = self._danger.get(key)
        if found is not None:
            return found
        out: dict[HexRef, int] = {}
        if self.params.danger_cost:
            infantry = self._enemy_infantry(state)
            friends = key[1]
            for here in self.engine.board.order:
                if any(geometry.distance(here, h) < self.params.standoff for h in infantry) and not self._escorted(friends, here):
                    out[here] = self.params.danger_cost
        self._danger = {key: out}
        return out

    def _field(self, state: State, vehicle, seeds: tuple[tuple[HexRef, int], ...], blocked: frozenset[HexRef] = frozenset()) -> dict[HexRef, int]:
        """The cost in movement halves from each hex to the best goal, over the vehicle
        entry costs of the core, for a vehicle of this type. Each goal starts at its own
        cost (`goal_costs`).

        A route does not go through a hex of `blocked`, the hexes that `_best_step` does not
        enter. A route through one gave a hex a cost that no step could reach, and an
        assault gun behind a tank of its own side stood there for four turns.
        """
        key = (self._key(state), vehicle.type_key, seeds, blocked)
        found = self._fields.get(key)
        if found is not None:
            return found
        board = self.engine.board
        danger = self._danger_map(state)
        dist: dict[HexRef, int] = {}
        heap = [(cost, g) for g, cost in seeds]
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
                heapq.heappush(heap, (d + cost + danger.get(here, 0), there))
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

    # ------------------------------------------------------------------- the section

    def _mobile(self, state: State) -> list:
        """The own vehicles that can still drive, in the order of their id."""
        return sorted(
            (u for u in state.player_units(self.player)
             if u.is_vehicle and u.hex is not None and not u.wreck and not u.eliminated and not u.immobilized),
            key=lambda u: u.id,
        )

    def _taken(self, state: State, vehicle) -> frozenset[HexRef]:
        # Rule 30.8: a vehicle may not stop where another working vehicle stands, so a hex
        # that holds one of this side's other vehicles is no goal and no step for this one.
        return frozenset(
            u.hex for u in state.player_units(self.player)
            if u.is_vehicle and u.id != vehicle.id and u.hex is not None and not u.wreck and not u.eliminated
        )

    def _route(self, state: State, vehicle) -> tuple[dict[HexRef, int], frozenset[HexRef]]:
        """The route field of this vehicle, and the hexes it may not enter."""
        taken = self._taken(state, vehicle)
        positions = self.firing_positions(state)
        if positions:
            costs = self.goal_costs(state)
            seeds = tuple((h, costs.get(h, 0)) for h in sorted(positions - taken))
        else:
            seeds = tuple((h, 0) for h in sorted(frozenset(self._objectives()) - taken))
        blocked = taken | frozenset(self._enemy_infantry(state))
        field = self._field(state, vehicle, seeds, blocked) if seeds else {}
        return field, taken

    def _holds(self, state: State, vehicle) -> bool:
        """A tank in a firing position holds there, unless the route offers another one that
        is `hold_margin` halves better (P4, P13)."""
        if vehicle.hex is None or vehicle.hex not in self.firing_positions(state):
            return False
        own = self.goal_costs(state).get(vehicle.hex, 0)
        field, _ = self._route(state, vehicle)
        return own - field.get(vehicle.hex, own) <= self.params.hold_margin

    def _in_contact(self, state: State, vehicle) -> bool:
        return any(geometry.distance(vehicle.hex, u.hex) <= self.params.contact_range for u in self._enemies(state))

    def _watchers(self, state: State, vehicle, mobile: list) -> list[HexRef]:
        """The hexes of the other own tanks that hold a firing position and did not move in
        this phase: the overwatch of this tank's bound (P7)."""
        return [
            u.hex for u in mobile
            if u.id != vehicle.id and not u.moved and u.hex in self.firing_positions(state) and self._holds(state, u)
        ]

    def _may_bound(self, state: State, vehicle, mobile: list) -> bool:
        """P7: in contact, the section moves by halves. The half of the turn bounds; the
        other half watches, and a tank of it moves only while another tank holds a firing
        position and watches it.

        The first rule let a tank move whenever any tank of its own held a position. The
        position of a watcher changed when the infantry moved or broke, the watcher then
        moved too, and the whole section moved in 22 of 56 phases in contact.
        """
        if not self.params.bound or len(mobile) < 2 or not self._in_contact(state, vehicle):
            return True
        if vehicle.hex in self._danger_map(state):
            # P13: a tank in the anti-tank range of enemy infantry with no escort pulls
            # back now; it does not wait for the turn of its half.
            return True
        if all(u.moved for u in mobile if u.id != vehicle.id):
            # The last tank that stands is the watch of the section. In turn 8 of the
            # balanced scenario 4 (2026-10-14) tank 13 bounded while tank 11 watched, and then
            # tank 11 left its position in the turn of its half, so no tank watched.
            return False
        ids = [u.id for u in mobile]
        index = ids.index(vehicle.id) if vehicle.id in ids else 0
        if index % 2 == state.turn % 2:
            return True
        return bool(self._watchers(state, vehicle, mobile))

    def _movers(self, state: State) -> set[int]:
        """The own tanks that will leave their hex in this player turn."""
        if not self.params.bound:
            return {u.id for u in self._mobile(state) if not self._holds(state, u)}
        mobile = self._mobile(state)
        return {u.id for u in mobile if not self._holds(state, u) and self._may_bound(state, u, mobile)}

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
            # Rule 30.8: a vehicle may not stop where another vehicle or a wreck stands, and
            # the core keeps the phase open until it leaves, so it leaves first.
            for vehicle_id in sorted(moves):
                vehicle = state.units[vehicle_id]
                if vehicle.hex is not None and r30_vehicle_movement.must_leave(state, vehicle):
                    out = self._best_step(state, vehicle, moves[vehicle_id], leaving=True)
                    if out is not None:
                        return out.id
            mobile = self._mobile(state)
            for vehicle_id in sorted(moves):
                vehicle = state.units[vehicle_id]
                if vehicle.hex is None:
                    continue
                if self._holds(state, vehicle):
                    continue  # it holds here and fires
                if not self._may_bound(state, vehicle, mobile):
                    continue  # it watches the other half of the section bound
                # PR-54: the overrun is declared on entry and resolves at the end of the
                # Defensive Fire Phase. A vehicle that has one declared gains nothing from a
                # second entry; a T-34 of v6 drove into and out of one hex 12 times in a phase.
                for lc in sorted(moves[vehicle_id], key=lambda lc: lc.id):
                    if vehicle.overrun_hex is None and lc.command.hex is not None and self._weak_overrun(state, lc.command.hex):
                        return lc.id
                watchers = self._watchers(state, vehicle, mobile) if self.params.bound else []
                best = self._best_step(state, vehicle, moves[vehicle_id], watchers=watchers)
                if best is not None:
                    return best.id
        return self._aim(state, by_action)

    def _best_step(self, state: State, vehicle, moves: list[LegalCommand], leaving: bool = False, watchers: list[HexRef] | None = None) -> LegalCommand | None:
        """The move one hex down the route field. With `leaving` the vehicle must leave its
        hex, so the best move goes even when it does not shorten the route. With `watchers`
        a step goes no farther than `overwatch_range` from the nearest of them (P7), unless
        it comes nearer to them."""
        field, taken = self._route(state, vehicle)
        danger = self._danger_map(state)
        # The cost of a move is the step itself (its entry cost and the risk of the breakdown
        # die) and the route from where it ends. The field holds only the route, so a step
        # into a wood that ended one hex nearer looked as good as a step on open ground, and
        # two German tanks drove into the woods on their first turn and broke down.
        best: LegalCommand | None = None
        here = field.get(vehicle.hex, UNREACHABLE)
        best_cost = 2 * UNREACHABLE + 1 if leaving else (here + 1 if here < UNREACHABLE else UNREACHABLE)
        reach = None
        if watchers:
            reach = max(self.params.overwatch_range, min(geometry.distance(vehicle.hex, w) for w in watchers))
        for lc in sorted(moves, key=lambda lc: lc.id):
            dst = lc.command.hex
            if dst is None or dst in taken or r30_vehicle_movement.enemy_infantry_in(state, self.player, dst):
                continue
            if reach is not None and not leaving and min(geometry.distance(dst, w) for w in watchers) > reach:
                continue
            rest = field.get(dst, UNREACHABLE)
            step = self._step_cost(state, vehicle, vehicle.hex, dst)
            cost = rest + (UNREACHABLE if step is None else step + danger.get(dst, 0))
            if cost < best_cost:
                best, best_cost = lc, cost
        return best

    def _threat_rank(self, state: State, unit, enemy) -> tuple[int, int, HexRef]:
        """P4: the order of the threats a tank turns its front to: an enemy gun in range,
        then an enemy anti-tank weapon near, then the nearest enemy."""
        distance = geometry.distance(unit.hex, enemy.hex)
        types = self.engine.types
        if enemy.is_vehicle and types[enemy.type_key].gun > 0 and not enemy.disabled and distance <= self.params.fire_range:
            return (0, distance, enemy.hex)
        if enemy.is_infantry and distance <= self.params.standoff + 2 and r37_at_weapons.anti_tank_weapons(state, types, enemy):
            return (1, distance, enemy.hex)
        return (2, distance, enemy.hex)

    def _aim(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str | None:
        """Rule 30.5: a vehicle that holds turns its front to the largest threat it does not cover."""
        if not self.params.pivot_to_aim:
            return None
        enemies = self._enemies(state)
        if not enemies:
            return None
        for lc in sorted(by_action.get("vehicle_pivot", []), key=lambda lc: lc.id):
            unit = state.units[lc.command.units[0]]
            if unit.hex is None or unit.pivoted:
                continue
            near = min((self._threat_rank(state, unit, e) for e in enemies))[2]
            if r28_vehicles.in_covered_arc(unit.hex, unit.facing, near):
                continue
            facing = int(dict(lc.command.extra).get("facing", -1))
            if facing >= 0 and r28_vehicles.in_covered_arc(unit.hex, facing, near):
                return lc.id
        return None
