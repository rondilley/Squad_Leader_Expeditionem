"""Scripted agent v7: the doctrine agent. It trades on the odds.

Agent v6 attacks on a schedule and wins the attack of scenario 1 against a random defender.
Against a defender that fires (v1, v4, v5) it wins 8 to 14 games in 20, and the probe of
seed 7 (VIBE_HISTORY, 2026-09-18) shows why: the Russian force closes to point blank range
on turn 1, and then the German prep fire and defensive fire break or kill three to nine
Russian squads in each player turn, most of them in stone buildings under a minus two
leader, while the Russian fire goes out in seven small groups of four to twelve firepower
against a plus three. The Russian has the numbers and spends them badly.

RV-9 section 5 (table A) turns the doctrine into numbers, and each number is the expected
result of a fire. `slagents.scripted.odds` gives that number from the tables of the core,
with no die. Agent v7 reads it in five places:

1. Concentration, and no overkill (P2). A fire group forms at the target where the
   expected loss of the enemy is highest, and it adds the member with the best marginal
   gain while that gain is worth a share of a squad (`overkill_share`). The next group goes
   to the next target. A shot worth less than `fire_floor` is not taken: it marks the
   unit as fired for nothing, and in the Prep Fire Phase it costs the move (rule 8.1).
2. The leader is a target (P12). The worth of a unit in the odds puts a 9-2 leader above
   two squads, so the group fires at the hex with the leader when the odds are close.
3. The base of fire covers the maneuver element (P1, P3). The v5 suppression value lifts
   the worth of a target that can see and hit our own units, and v6 keeps the pressed
   units out of the prep fire, so the shooters fire and the movers move.
4. The route is the expected loss (P7, P8). The threat of a hex is the chance that a squad
   standing in it breaks under the fire of every unbroken enemy that can see it, with the
   terrain of the hex, the minus two of rule 16.5 for a move in the open, and the best
   enemy leader. That is what v6 approximated with a count of squads and a halving for
   cover, and the table is not linear: a stone building is worth five columns of dice
   against an open street, not a factor of four.
5. The defender catches the mover in the open (P21, the inverse of P8). Rule 16.1 lets
   the defender put a moved unit back on a hex of its track. Agent v1 did that after it
   had fired, for nothing. Agent v7 compares the best shot at each track hex with the
   best shot at the end hex, and returns the unit when the open ground pays.

Close combat reads the odds too. Rule 20.9 eliminates a broken unit in a melee hex, so
an advance into a hex of broken enemies is a sure kill (P18, pursue), and a declared
attack is favorable when the chance of our kill is above the chance of theirs.

The nation profiles are the v6 profiles with the v7 numbers. The American profile leans
on fire (a lower floor, a wider group). The German profile is aggressive in close combat.
The Soviet profile presses first and accepts the loss.

What v7 does not do yet: it has no reserve (P19), it does not block a rout (P11), it uses
no smoke (P15), and it has no policy for a vehicle, so the tanker v3 drives them.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, replace

from slcore import geometry
from slcore.engine import Engine
from slcore.frame import DecisionFrame, LegalCommand
from slcore.game import PHASE_DEFENSIVE_FIRE, PHASE_MOVEMENT, PHASE_PREP_FIRE, FireGroup, State
from slcore.geometry import HexRef
from slcore.los_eval import evaluate as evaluate_los
from slcore.rules import r05_movement, r08_fire, r10_resolution, r13_rout, r20_close_combat
from slcore.rules.r11_terrain import is_open_ground
from slcore.rules.r13_rout import is_cover
from slcore.units import KIND_LEADER, KIND_SW, Unit

from slagents.scripted import odds
from slagents.scripted.v6 import ENEMY_HEX_HALVES
from slagents.scripted.v6 import Parameters as V6Parameters
from slagents.scripted.v6 import ScriptedV6

# The odds are counts out of `odds.ONE`. A "squad" of value is one squad of four firepower
# that breaks for certain: eight halves times ONE.
SQUAD = 8 * odds.ONE
# The most members a plan considers for one target, by their solo firepower.
PLAN_CANDIDATES = 8
# The suppression lift of a target counts the units of ours it can hit, up to this many.
SUPPRESSION_CAP = 6
# Another unit of ours competes for the defender's fire when its exposure is at least this
# share of the unit in question.
SHARE_FLOOR_PERCENT = 80


@dataclass(frozen=True)
class Parameters:
    """The named parameters of v7. It is a superset of the v6 parameters (FR-44)."""

    aggression: int = 2
    cover_preference: int = 3
    fire_priority: int = 2
    group_size: int = 6
    advance_into_close_combat: bool = True
    threat_aversion: int = 1
    close_combat_superiority: int = 2
    superiority_tenths: int = 15
    suppression_priority: int = 2
    threat_scale: int = 8
    schedule_margin: int = 2
    route_risk: int = 2
    # v7 adds these:
    fire_floor: int = 2  # percent of a squad break: a group fires only above this
    fire_weight: int = 2  # score points of one half of expected enemy loss from a position
    overkill_share: int = 5  # percent of a squad break each member of a group has to add
    loss_scale: int = 16  # score points of a whole squad lost, in the step score
    route_loss: int = 24  # movement halves of a whole squad lost, on the route
    return_margin: int = 10  # percent of a squad break a track return has to add
    close_combat_margin: int = 10  # percent: our kill chance above theirs for an assault
    urgency_cap: int = 4  # the most a hex of progress is worth, in multiples of the aggression
    suicide_percent: int = 100  # a pressed unit does not force a step whose loss chance is above this
    spare_targets: int = 2  # places the plan takes past the swing margin
    garrison_hexes: int = 2  # hexes of distance a garrison squad adds to a target, for each unit
    share_fire: bool = False  # the exposure counts the share of the defender's groups (mass)
    share_targets: int = 2  # the targets one enemy group is worth in the share
    rout_block: bool = True  # an advance that traps a broken enemy earns its worth (P11)
    rout_by_loss: bool = True  # a broken unit routs to the cover with the lowest loss, and to a leader
    dash_arrives: bool = True  # a forced run happens only when it reaches the target this turn
    setup_by_odds: bool = False  # a unit sets up in the hex of its zone with the best fire and the least loss; it lost on the measure
    field_weight: int = 1  # score points for each four open hexes a defender sees from its set up hex


NATION_PROFILES: dict[str, Parameters] = {
    "german": Parameters(aggression=3, cover_preference=3, threat_aversion=1, superiority_tenths=13, schedule_margin=2, close_combat_margin=0),
    "soviet": Parameters(aggression=3, cover_preference=2, threat_aversion=1, superiority_tenths=12, suppression_priority=1, schedule_margin=3, loss_scale=9),
    "american": Parameters(aggression=2, cover_preference=4, fire_priority=3, threat_aversion=2, superiority_tenths=18, suppression_priority=3, schedule_margin=1, fire_floor=3, group_size=7),
}


class UnknownNation(Exception):
    """The nation profile is not defined. British waits for its research pass."""


def profile_for(nation: str) -> Parameters:
    key = nation.strip().lower()
    if key not in NATION_PROFILES:
        raise UnknownNation(
            f"no v7 profile for {nation!r}. Defined: {', '.join(sorted(NATION_PROFILES))}. "
            f"British is not confirmed yet and waits for a follow-up research pass."
        )
    return NATION_PROFILES[key]


def with_parameters(**changes: object) -> Parameters:
    return replace(Parameters(), **changes)


def parameters_from_text(text: str, base: Parameters | None = None) -> Parameters:
    """The parameters from `name=value,name=value`, for a study from the command line.

    A name that is not a parameter, or a value that is not a whole number, is an error
    that names the parameter, so a typo in a study does not run the default in silence.
    """
    params = base or Parameters()
    changes: dict[str, object] = {}
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"a v7 parameter is name=value, and {part!r} has no value")
        name, value = (piece.strip() for piece in part.split("=", 1))
        if not hasattr(params, name):
            raise ValueError(f"v7 has no parameter {name!r}; the names are {', '.join(sorted(vars(params)))}")
        current = getattr(params, name)
        if isinstance(current, bool):
            changes[name] = value.lower() in ("1", "true", "yes", "on")
        else:
            try:
                changes[name] = int(value)
            except ValueError as exc:
                raise ValueError(f"the v7 parameter {name!r} takes a whole number, not {value!r}") from exc
    return replace(params, **changes)


@dataclass(frozen=True)
class Plan:
    """A fire plan for one target: the members in the order they join, and its worth."""

    target: HexRef
    members: tuple[LegalCommand, ...]
    value: int  # the worth, with the lift for a target that covers our force
    raw: int  # the expected loss of the enemy alone


class ScriptedV7(ScriptedV6):
    name = "scripted"
    version = "7"

    def __init__(self, engine: Engine, player: int, params: Parameters | None = None) -> None:
        self.v7 = params or Parameters()
        p = self.v7
        super().__init__(
            engine,
            player,
            V6Parameters(
                aggression=p.aggression,
                cover_preference=p.cover_preference,
                fire_priority=p.fire_priority,
                group_size=p.group_size,
                advance_into_close_combat=p.advance_into_close_combat,
                threat_aversion=p.threat_aversion,
                close_combat_superiority=p.close_combat_superiority,
                superiority_tenths=p.superiority_tenths,
                suppression_priority=p.suppression_priority,
                threat_scale=p.threat_scale,
                schedule_margin=p.schedule_margin,
                route_risk=p.route_risk,
            ),
        )
        # The expected loss of a unit in each hex, and the fire a unit gives from each hex,
        # for this enemy picture.
        self._loss_map: dict[tuple, int] = {}
        self._fire_map: dict[tuple, int] = {}
        # The movement halves along the path of each route field, by field.
        self._moves_along: dict[tuple[tuple[HexRef, ...], bool], dict[HexRef, int]] = {}
        # The exposure of each of our units for the decision in hand.
        self._exposure_key: tuple = ()
        self._exposure_now: dict[int, int] = {}

    # ------------------------------------------------------------------ the plan

    def _targets_wanted(self) -> int:
        """The places the plan takes at one time: the swing margin plus the spare.

        v6 takes one past the margin, so a building lost cancels nothing. With five turns
        and a garrison in each building, the force that divides three ways takes none in
        time. `spare_targets` sets the spare, and zero puts the whole force on the margin
        (P5, mass against the weak part).
        """
        wanted = super()._targets_wanted()
        if wanted <= 0:
            return wanted
        return max(1, wanted - 1 + self.v7.spare_targets)

    def _target_order(self, state: State, free: list[Unit], open_places: list[tuple[str, tuple[HexRef, ...]]]) -> list[tuple[str, tuple[HexRef, ...]]]:
        """The open places by the distance of the force plus the garrison that holds each,
        so the plan goes for the near and the weak (P5, P14). A garrison squad counts as
        `garrison_hexes` hexes of distance for each unit of the force."""

        def cost(place: tuple[str, tuple[HexRef, ...]]) -> tuple[int, str]:
            total = sum(min(geometry.distance(u.hex, h) for h in place[1]) for u in free)
            garrison = sum(
                1
                for h in place[1]
                for u in state.infantry_in(h)
                if u.player == self.opponent and not u.broken and u.kind != KIND_LEADER
            )
            return (total + garrison * self.v7.garrison_hexes * max(1, len(free)), place[0])

        return sorted(open_places, key=cost)

    # ------------------------------------------------------------------ the odds

    def _refresh_routes(self, state: State) -> None:
        before = self._picture
        super()._refresh_routes(state)
        if self._picture != before:
            self._loss_map = {}
            self._fire_map = {}
            self._moves_along = {}

    def _enemy_groups(self, state: State, dst: HexRef) -> list[tuple[tuple[tuple[int, int | None], ...], int | None]]:
        """The fire groups the enemy could form against a hex, with the best leader of each.

        Rule 8.6 chains the members of a group through adjacent hexes, so the shooters
        that see the hex fall into clusters of adjacent hexes, and each cluster is one
        group.
        """
        types = self.engine.types
        by_hex: dict[HexRef, list[tuple[int, int | None]]] = {}
        leaders: dict[HexRef, Unit] = {}
        for enemy in state.player_units(self.opponent):
            if enemy.hex is None or enemy.broken or enemy.is_vehicle or enemy.hex == dst:
                continue
            if not evaluate_los(self.engine.board, self.engine.los, enemy.hex, dst).clear:
                continue
            if enemy.kind == KIND_LEADER:
                held = leaders.get(enemy.hex)
                if held is None or types[enemy.type_key].leadership < types[held.type_key].leadership:
                    leaders[enemy.hex] = enemy
                continue
            if r08_fire.member_firepower(state, types, enemy, None, dst, False) is not None:
                by_hex.setdefault(enemy.hex, []).append((enemy.id, None))
            for weapon in state.carried_by(enemy.id):
                if weapon.kind != KIND_SW or weapon.broken or weapon.malfunction:
                    continue
                if r08_fire.member_firepower(state, types, enemy, weapon, dst, False) is not None:
                    by_hex.setdefault(enemy.hex, []).append((enemy.id, weapon.id))
        groups: list[tuple[tuple[tuple[int, int | None], ...], int | None]] = []
        left = set(by_hex)
        while left:
            start = min(left)
            cluster = [start]
            left.discard(start)
            i = 0
            while i < len(cluster):
                for near in self.engine.board.neighbors(cluster[i]):
                    if near in left:
                        left.discard(near)
                        cluster.append(near)
                i += 1
            members: list[tuple[int, int | None]] = []
            leader: Unit | None = None
            for h in sorted(cluster):
                members.extend(by_hex[h])
                candidate = leaders.get(h)
                if candidate is not None and (leader is None or types[candidate.type_key].leadership < types[leader.type_key].leadership):
                    leader = candidate
            groups.append((tuple(members), None if leader is None else leader.id))
        return groups

    def _loss(self, state: State, unit: Unit, dst: HexRef, moving: bool) -> int:
        """The chance, out of `odds.ONE`, that this unit breaks or dies in `dst` under the
        fire of each enemy group that sees the hex. With `moving` the fire is the Defensive
        Fire Phase at a unit that moved there, so open ground costs the minus two of rule
        16.5. The worst group sets the chance, because the defender spreads its groups over
        many targets and one hex draws one of them."""
        key = (dst, moving, unit.type_key, unit.broken)
        found = self._loss_map.get(key)
        if found is not None:
            return found
        groups = self._enemy_groups(state, dst)
        if not groups:
            self._loss_map[key] = 0
            return 0
        stand_in = unit.with_(hex=dst, moved=moving, returned_from=None)
        # The odds read the leaders that stand in the target hex for the check, and the
        # mover brings none with it, so the others of the hex are out of the picture.
        others = {u.id: u.with_(hex=None) for u in state.infantry_in(dst) if u.player == self.player and u.id != unit.id}
        hypothetical = state.with_units({unit.id: stand_in, **others})
        phase = PHASE_DEFENSIVE_FIRE if moving else PHASE_PREP_FIRE
        # The defender has more targets than groups, so one group is what a hex draws:
        # the chance is the worst group and not the product of all of them.
        chance = 0
        for members, leader in groups:
            result = odds.shot(self.engine, hypothetical, FireGroup(dst, members, leader), phase)
            chance = max(chance, result.breaks.get(unit.id, 0))
        self._loss_map[key] = chance
        return chance

    def _fire_value(self, state: State, unit: Unit, dst: HexRef) -> int:
        """The expected loss of the enemy, in halves times `odds.ONE`, from the best shot
        this unit alone takes from `dst` at any enemy hex it sees and reaches.

        A position is worth the fire it gives (RV-9 P3, P21). A unit that stands where it
        cannot fire is out of the fight, and the loss model alone sends every unit to the
        dead ground where it is safe and useless.
        """
        if unit.kind == KIND_LEADER or unit.broken:
            return 0
        weapons = tuple(w.id for w in state.carried_by(unit.id) if w.kind == KIND_SW and not w.broken and not w.malfunction)
        key = (dst, unit.type_key, weapons)
        found = self._fire_map.get(key)
        if found is not None:
            return found
        types = self.engine.types
        best = 0
        stand_in = unit.with_(hex=dst, moved=False, returned_from=None)
        changed = {unit.id: stand_in}
        for wid in weapons:
            changed[wid] = state.units[wid].with_(hex=dst)
        hypothetical = state.with_units(changed)
        for target in r10_resolution.enemy_occupied_hexes(hypothetical, self.player):
            if target == dst:
                continue
            if r08_fire.member_firepower(hypothetical, types, stand_in, None, target, False) is None and not any(
                r08_fire.member_firepower(hypothetical, types, stand_in, hypothetical.units[w], target, False) is not None for w in weapons
            ):
                continue
            if not evaluate_los(self.engine.board, self.engine.los, dst, target).clear:
                continue
            members = [(unit.id, None)] + [(unit.id, w) for w in weapons]
            value = odds.shot(self.engine, hypothetical, FireGroup(target, tuple(members), None), PHASE_PREP_FIRE).value
            if value > best:
                best = value
        self._fire_map[key] = best
        return best

    def _fire_points(self, state: State, unit: Unit, dst: HexRef) -> int:
        """The fire a position gives, in score points. A lift for the friends next to the
        position (mass, P5) was measured and lost: the squads bunched in one hex, and
        one KIA result took the stack."""
        return self._fire_value(state, unit, dst) * self.v7.fire_weight // odds.ONE

    def _reference_unit(self, state: State) -> Unit | None:
        """The squad the route is measured for: the most common squad type of this side."""
        counts: dict[str, int] = {}
        first: dict[str, Unit] = {}
        for u in state.player_units(self.player):
            if u.kind == "squad" and not u.broken and u.hex is not None:
                counts[u.type_key] = counts.get(u.type_key, 0) + 1
                first.setdefault(u.type_key, u)
        if not counts:
            return None
        best = max(sorted(counts), key=lambda k: counts[k])
        return first[best]

    # ------------------------------------------------------------------ the route

    def _route_field(self, state: State, target: tuple[HexRef, ...], safe: bool = True) -> dict[HexRef, int]:
        """The v6 field, and for the safe field the movement halves along its path too.

        The safe field counts the risk of a hex as cost, so its cost is not a time. The
        schedule needs the time of the covered route, which is the movement along the
        path the field chose. `_moves_along` holds it for each hex.
        """
        found = self._fields.get((target, safe))
        if found is not None:
            return found
        board = self.engine.board
        ctx = self.engine.move_ctx
        enemy_hexes = {u.hex for u in state.player_units(self.opponent) if u.hex is not None and not u.broken and u.is_infantry}
        targets = set(target)
        dist: dict[HexRef, int] = {}
        moves: dict[HexRef, int] = {}
        heap: list[tuple[int, int, HexRef]] = [(0, 0, t) for t in target if t in board]
        heapq.heapify(heap)
        while heap:
            d, m, k = heapq.heappop(heap)
            if k in dist:
                continue
            dist[k] = d
            moves[k] = m
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
                heapq.heappush(heap, (d + cost + enter_k, m + cost, h))
        self._fields[(target, safe)] = dist
        self._moves_along[(target, safe)] = moves
        return dist

    def _route_time(self, state: State, target: tuple[HexRef, ...], hex_ref: HexRef, safe: bool) -> int:
        """The movement halves of the route from the hex, along the path of the field."""
        self._route_field(state, target, safe)
        found = self._moves_along[(target, safe)].get(hex_ref)
        if found is None:
            return 2 * min(geometry.distance(hex_ref, o) for o in target) + 1000
        return found

    def _hex_risk(self, state: State, hex_ref: HexRef) -> int:
        """The expected loss of a squad that moves into the hex, in movement halves."""
        reference = self._reference_unit(state)
        if reference is None:
            return 0
        return self._loss(state, reference, hex_ref, True) * self.v7.route_loss // odds.ONE

    def _raw_exposure(self, state: State, unit: Unit, dst: HexRef | None, moving: bool) -> int:
        """The chance the unit is lost to the fire of the phase, out of `odds.ONE`, as the
        only target on the board.

        Rule 16.1 lets the defender fire at any hex of the track of a moved unit, so in
        the Movement Phase the exposure of a move is the worst hex of the track and the
        destination, and a step out of the open into cover takes nothing back. In the
        Advance Phase the track is paid: the Defensive Fire Phase is over, and the step
        faces the prep fire of the next enemy turn where it stands (rule 4). A unit that
        stands still is fired at where it stands.
        """
        worst = 0
        in_movement = state.phase == PHASE_MOVEMENT
        if in_movement and (moving or unit.moved):
            for h in unit.track:
                worst = max(worst, self._loss(state, unit, h, True))
        if dst is not None:
            worst = max(worst, self._loss(state, unit, dst, in_movement and (moving or unit.moved)))
        return worst

    def _exposure(self, state: State, unit: Unit, dst: HexRef | None, moving: bool) -> int:
        """The exposure with the share of the defender's fire (P5, mass).

        Each enemy group fires one time in a phase, at one hex, so `groups` targets of
        ours take the fire and the rest do not. The share of this unit is the count of
        groups that see its hex over the count of our units that are at least as good a
        target this phase, and itself. The first unit into the street pays in full. The
        tenth pays a tenth, which is why an assault goes in as one wave and not one
        squad at a time.
        """
        chance = self._raw_exposure(state, unit, dst, moving)
        if chance <= 0 or dst is None or not self.v7.share_fire:
            return chance
        # Each group fires one time, but a group breaks a stack and a broken target
        # frees the next group for another, so a group is worth `share_targets` targets.
        groups = len(self._enemy_groups(state, dst)) * self.v7.share_targets
        if groups <= 0:
            return chance
        competitors = 0
        floor = chance * SHARE_FLOOR_PERCENT // 100
        for other, other_chance in self._exposures_now(state).items():
            if other != unit.id and other_chance >= floor:
                competitors += 1
        if competitors + 1 <= groups:
            return chance
        return chance * groups // (competitors + 1)

    def _exposures_now(self, state: State) -> dict[int, int]:
        """The exposure of each unbroken infantry unit of ours where it stands, for this
        decision. In the Movement Phase a unit that moved is exposed on its track."""
        key = (state.seq, state.phase)
        if self._exposure_key == key:
            return self._exposure_now
        out: dict[int, int] = {}
        for u in state.player_units(self.player):
            if u.hex is None or u.broken or not u.is_infantry or u.carrier is not None:
                continue
            out[u.id] = self._raw_exposure(state, u, u.hex, False)
        self._exposure_key = key
        self._exposure_now = out
        return out

    def _penalty(self, state: State, unit: Unit, dst: HexRef, moving: bool, count: int) -> int:
        chance = self._exposure(state, unit, dst, moving)
        return chance * self.v7.loss_scale * max(1, count) // odds.ONE

    # ------------------------------------------------------------- the schedule

    def _slack_on(self, state: State, unit_id: int, unit_hex: HexRef, safe: bool) -> int:
        """Turns of slack on one route field: the turns left, minus the turns the route
        needs. The safe field counts the risk of each hex as movement, so its slack is
        the time the covered approach (P8) leaves."""
        target = self.assignment.get(unit_id, self.open_objectives)
        cost = self._route_time(state, target, unit_hex, safe=safe)
        if cost >= 1000:
            cost = 2 * self._unit_distance(unit_id, unit_hex)
        per_turn = max(2, self.engine.types[state.units[unit_id].type_key].mf_halves + 2)
        needed = (cost + per_turn - 1) // per_turn
        return self._turns_left(state) - needed

    def _press_level(self, state: State, unit_id: int, unit_hex: HexRef) -> int:
        """0: the unit has time. 1: the covered route has to start now (P8), and a step
        along it earns a bonus. 2: only the fastest route arrives in time, so the unit
        takes it and pays (P17, tempo): a step with a gain beats the stand."""
        if not self.has_deadline or self._unit_distance(unit_id, unit_hex) == 0:
            return 0
        if self._slack_on(state, unit_id, unit_hex, safe=False) < self.v6.schedule_margin:
            return 2
        if self._slack_on(state, unit_id, unit_hex, safe=True) < self.v6.schedule_margin:
            return 1
        return 0

    def _pressed(self, state: State, unit_id: int, unit_hex: HexRef) -> bool:
        """The unit has to run: only the fastest route arrives in time."""
        return self._press_level(state, unit_id, unit_hex) == 2

    # ----------------------------------------------------------- the step score

    def _step_score(self, state: State, unit_id: int, unit_hex: HexRef, dst: HexRef, cache: dict[HexRef, int], bonus: int = 0, count: int = 1, moving: bool = True) -> tuple[int, int]:
        """The v6 step score with the expected loss in place of the count of squads."""
        target = self.assignment.get(unit_id, self.open_objectives)
        level = self._press_level(state, unit_id, unit_hex)
        unit = state.units[unit_id]
        safe = level < 2
        gain = self._route_cost(state, target, unit_hex, safe) - self._route_cost(state, target, dst, safe)
        if safe and gain > 0:
            # The safe field holds the risk of the destination in its cost, and the step
            # pays that risk once, as the penalty below, and not as a gain as well.
            gain = max(0, gain - self._hex_risk(state, dst))
        cover = self.v6.cover_preference if is_cover(self.engine.board, dst) else 0
        exposure = self._exposure(state, unit, dst, moving)
        penalty = exposure * self.v7.loss_scale * max(1, count) // odds.ONE
        fire = self._fire_points(state, unit, dst)
        # Tempo (P17): a turn with no progress is a turn lost. The worth of a hex of
        # progress grows as the slack shrinks, so the attacker moves through low loss
        # early and accepts more loss late, in place of a wait and then a rush.
        urgency = self._urgency(state, unit_id, unit_hex)
        value = gain * self.v6.aggression * urgency + cover + fire + bonus - penalty * self.v6.threat_aversion
        # The unit that has to run takes a step with a gain over a stand, unless the step
        # is a death: a squad that is killed in the street takes no building either.
        forced = gain > 0 and level == 2 and exposure < odds.ONE * self.v7.suicide_percent // 100
        if forced and self.v7.dash_arrives and moving:
            # The run is forced only when the fastest route gets the unit to its target
            # in this turn. A run that ends in the street draws the fire of rule 16.1
            # and holds nothing. A step that is not forced is judged by its value.
            allowance = self.engine.types[unit.type_key].mf_halves - unit.mf_used + 2
            forced = self._route_time(state, target, unit_hex, safe=False) <= allowance
        pressed = 1 if forced else 0
        return (pressed, value)

    def _urgency(self, state: State, unit_id: int, unit_hex: HexRef) -> int:
        """How much a hex of progress is worth now: one with time to spare, up to
        `urgency_cap` when the fastest route has no slack left, and more when the enemy
        is down (P18, press: once ahead, press harder, before the broken rally)."""
        if not self.has_deadline or self._unit_distance(unit_id, unit_hex) == 0:
            return 1
        slack = self._slack_on(state, unit_id, unit_hex, safe=False)
        urgency = self.v6.schedule_margin + 2 - slack + self._exploit(state)
        return max(1, min(self.v7.urgency_cap, urgency))

    def _exploit(self, state: State) -> int:
        """The press of P18: the unbroken squads of this side against the enemy's. A ratio
        of two gives one step of urgency, a ratio of three gives two."""
        ours = sum(1 for u in state.player_units(self.player) if u.kind == "squad" and not u.broken and u.hex is not None)
        theirs = sum(1 for u in state.player_units(self.opponent) if u.kind == "squad" and not u.broken and u.hex is not None)
        if theirs == 0:
            return 2
        if ours >= 3 * theirs:
            return 2
        if ours >= 2 * theirs:
            return 1
        return 0

    def _stand_value(self, state: State, unit_id: int, cache: dict[HexRef, int]) -> int:
        unit = state.units[unit_id]
        if unit.hex is None:
            return 0
        cover = self.v6.cover_preference if is_cover(self.engine.board, unit.hex) else 0
        # One unit decides for itself: the others of the stack make their own choice, and
        # a stand that pays for the whole stack sends each unit out into the open alone.
        fire = self._fire_points(state, unit, unit.hex)
        return cover + fire - self._penalty(state, unit, unit.hex, False, 1) * self.v6.threat_aversion

    # ------------------------------------------------------------------- the fire

    def _fire(self, state: State, frame: DecisionFrame, by_action: dict[str, list[LegalCommand]]) -> str:
        phase = frame.phase
        if phase == PHASE_DEFENSIVE_FIRE and state.fire_group is None and "track_return" in by_action:
            returned = self._best_track_return(state, by_action)
            if returned is not None:
                return returned
        group = state.fire_group
        if group is not None:
            return self._continue_group(state, group, by_action, phase)
        # A shot from a unit that stands is free, so the floor is a token: it stops a
        # group that cannot hurt the target at all. Rule 8.1 holds a unit that prep
        # fires in its hex for the Movement Phase (it still advances, rule 4.7). So a
        # unit whose best step beats its stand joins a group only when the expected loss
        # of the enemy, in the points of the step score, is worth the step it gives up.
        # That is the base of fire and the maneuver element in one currency (P1, P3).
        floor = SQUAD * self.v7.fire_floor // 100
        if phase == PHASE_PREP_FIRE and self.has_deadline:
            shooters = {lc.command.units[0] for lc in by_action.get("group_add", []) + by_action.get("group_add_weapon", [])}
            advantage = {u: self._move_advantage(state, state.units[u]) for u in shooters}
            standing = {u for u, a in advantage.items() if a <= 0}
            plan = self._best_plan(state, self._kept(by_action, standing), phase)
            if plan is not None and plan.raw >= floor:
                return plan.members[0].id
            plan = self._best_plan(state, by_action, phase)
            if plan is not None and plan.raw >= floor:
                cost = max(advantage.get(lc.command.units[0], 0) for lc in plan.members)
                if plan.raw * self.v7.fire_weight // odds.ONE >= cost:
                    return plan.members[0].id
            return self._first_of(by_action, ("end_phase",))
        plan = self._best_plan(state, by_action, phase)
        if plan is None or plan.raw < floor:
            return self._first_of(by_action, ("end_phase",))
        return plan.members[0].id

    def _move_advantage(self, state: State, unit: Unit) -> int:
        """How much the best step of the coming Movement Phase beats the stand, in the
        points of the step score. Zero when no step beats it.

        The prep fire decision comes before the move, so the agent reads its own move
        rule on the neighbours of the hex, with the stacking limit of rule 6.1. A unit
        that has to run counts a step with a gain as a whole squad of advantage.
        """
        if unit.hex is None or unit.broken:
            return 0
        cache: dict[HexRef, int] = {}
        stand = self._stand_value(state, unit.id, cache)
        ctx = self.engine.move_ctx
        best = 0
        for near in self.engine.board.neighbors(unit.hex):
            cost, _ = r05_movement.entry_cost_halves(ctx, unit.hex, near)
            if cost is None or any(u.player != self.player and not u.broken for u in state.infantry_in(near)):
                continue
            if self._would_overstack(state, near, (unit.id,)):
                continue
            pressed, value = self._step_score(state, unit.id, unit.hex, near, cache)
            if pressed > 0:
                best = max(best, self.v7.loss_scale)
            best = max(best, value - stand)
        return best

    @staticmethod
    def _kept(by_action: dict[str, list[LegalCommand]], units: set[int]) -> dict[str, list[LegalCommand]]:
        kept: dict[str, list[LegalCommand]] = {}
        for action, commands in by_action.items():
            if action in ("group_add", "group_add_weapon"):
                commands = [lc for lc in commands if lc.command.units[0] in units]
                if not commands:
                    continue
            kept[action] = commands
        return kept

    def _adds_by_target(self, by_action: dict[str, list[LegalCommand]]) -> dict[HexRef, list[LegalCommand]]:
        out: dict[HexRef, list[LegalCommand]] = {}
        for lc in by_action.get("group_add", []) + by_action.get("group_add_weapon", []):
            if lc.command.hex is not None:
                out.setdefault(lc.command.hex, []).append(lc)
        return out

    def _member_of(self, lc: LegalCommand) -> tuple[int, int | None]:
        return (lc.command.units[0], lc.command.weapon)

    def _worth(self, state: State, target: HexRef, value: int) -> int:
        """The worth of a shot: its expected loss, lifted up to two times when the target
        covers our force, so the base of fire breaks the defender that sees the movers."""
        threatened = min(SUPPRESSION_CAP, self._suppression_value(state, target)) * self.v7.suppression_priority
        return value * (SUPPRESSION_CAP * 2 + threatened) // (SUPPRESSION_CAP * 2)

    def _plan_for(
        self,
        state: State,
        target: HexRef,
        adds: list[LegalCommand],
        phase: str,
        base: tuple[tuple[int, int | None], ...] = (),
        leader: int | None = None,
    ) -> Plan | None:
        """The best group at one target from these adds, on top of the members in `base`.

        The members join in the order of the best marginal gain, and the plan reads every
        size of the group, because the table moves by columns: the third member can add
        what the second did not. The size that wins is the one where the expected loss of
        the enemy, less a share of a squad for each member (the member's other uses), is
        highest. That is the concentration of P2 and its limit, no overkill.
        """
        if not adds:
            return None
        solo: list[tuple[int, str, LegalCommand]] = []
        for lc in adds:
            halves = self._member_value(state, lc, target)
            if halves > 0:
                solo.append((-halves, lc.id, lc))
        solo.sort()
        candidates = [lc for _, _, lc in solo[:PLAN_CANDIDATES]]
        members = list(base)
        order: list[LegalCommand] = []
        values: list[int] = []
        while candidates and len(members) < self.v7.group_size:
            best: LegalCommand | None = None
            best_value = -1
            for lc in candidates:
                trial = FireGroup(target, tuple(members + [self._member_of(lc)]), leader)
                trial_value = odds.shot(self.engine, state, trial, phase).value
                if trial_value > best_value or (trial_value == best_value and best is not None and lc.id < best.id):
                    best, best_value = lc, trial_value
            if best is None:
                break
            members.append(self._member_of(best))
            order.append(best)
            values.append(best_value)
            candidates = [lc for lc in candidates if lc is not best]
        if not order:
            return None
        share = SQUAD * self.v7.overkill_share // 100
        best_k = 0
        best_net = None
        for k, value in enumerate(values, start=1):
            net = value - k * share
            if best_net is None or net > best_net:
                best_k, best_net = k, net
        value = values[best_k - 1]
        return Plan(target, tuple(order[:best_k]), self._worth(state, target, value), value)

    def _best_plan(self, state: State, by_action: dict[str, list[LegalCommand]], phase: str) -> Plan | None:
        best: Plan | None = None
        for target, adds in sorted(self._adds_by_target(by_action).items()):
            plan = self._plan_for(state, target, adds, phase)
            if plan is None:
                continue
            if best is None or plan.value > best.value:
                best = plan
        return best

    def _continue_group(self, state: State, group: FireGroup, by_action: dict[str, list[LegalCommand]], phase: str) -> str:
        """Add the next member of the plan, then the leader that lifts the odds, then fire."""
        adds = [lc for lc in by_action.get("group_add", []) + by_action.get("group_add_weapon", []) if lc.command.hex == group.target]
        current = odds.shot(self.engine, state, group, phase).value
        if adds and len(group.members) < self.v7.group_size:
            plan = self._plan_for(state, group.target, adds, phase, base=group.members, leader=group.leader)
            share = SQUAD * self.v7.overkill_share // 100
            if plan is not None and plan.raw - current >= share * len(plan.members):
                return plan.members[0].id
        leaders = by_action.get("group_leader", [])
        if leaders:
            best_leader: LegalCommand | None = None
            best_value = current
            for lc in leaders:
                trial = replace(group, leader=lc.command.units[0])
                trial_value = odds.shot(self.engine, state, trial, phase).value
                if trial_value > best_value or (trial_value == best_value and best_leader is not None and lc.id < best_leader.id):
                    best_leader, best_value = lc, trial_value
            if best_leader is not None:
                return best_leader.id
        return self._first_of(by_action, ("group_fire", "end_phase"))

    # ------------------------------------------------------------ the track return

    def _best_track_return(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str | None:
        """Rule 16.1: put the movers back where the fire catches them best.

        For each return the host offers, the odds of the best group at the track hex, with
        the movers standing there, against the odds of the best group at their end hexes.
        The return wins when it adds `return_margin` of a squad.
        """
        adds = by_action.get("group_add", []) + by_action.get("group_add_weapon", [])
        shooters = sorted({self._member_of(lc) for lc in adds}, key=lambda m: (m[0], -1 if m[1] is None else m[1]))
        if not shooters:
            return None
        best: LegalCommand | None = None
        best_gain = SQUAD * self.v7.return_margin // 100
        for lc in by_action["track_return"]:
            track_hex = lc.command.hex
            if track_hex is None:
                continue
            movers = [state.units[uid] for uid in lc.command.units]
            stay = 0
            for end_hex in sorted({u.hex for u in movers if u.hex is not None}):
                stay = max(stay, self._best_hypothetical(state, end_hex, shooters))
            moved = {u.id: u.with_(hex=track_hex, returned_from=u.hex) for u in movers}
            hypothetical = state.with_units(moved)
            there = self._best_hypothetical(hypothetical, track_hex, shooters)
            gain = there - stay
            if gain > best_gain or (gain == best_gain and best is not None and lc.id < best.id):
                best, best_gain = lc, gain
        return None if best is None else best.id

    def _best_hypothetical(self, state: State, target: HexRef, shooters: list[tuple[int, int | None]]) -> int:
        """The worth of the best group these shooters make at the target, by the odds."""
        types = self.engine.types
        able: list[tuple[int, int | None]] = []
        for uid, wid in shooters:
            unit = state.units[uid]
            if unit.hex is None or unit.hex == target:
                continue
            weapon = None if wid is None else state.units[wid]
            if r08_fire.member_firepower(state, types, unit, weapon, target, unit.moved) is None:
                continue
            if not evaluate_los(self.engine.board, self.engine.los, unit.hex, target).clear:
                continue
            able.append((uid, wid))
        if not able:
            return 0
        members: list[tuple[int, int | None]] = []
        values: list[int] = []
        while able and len(members) < self.v7.group_size:
            best = None
            best_value = -1
            for member in able:
                trial_value = odds.shot(self.engine, state, FireGroup(target, tuple(members + [member]), None), PHASE_DEFENSIVE_FIRE).value
                if trial_value > best_value:
                    best, best_value = member, trial_value
            if best is None:
                break
            members.append(best)
            values.append(best_value)
            able = [m for m in able if m != best]
        share = SQUAD * self.v7.overkill_share // 100
        best_net = max((value - k * share for k, value in enumerate(values, start=1)), default=0)
        return self._worth(state, target, max(0, best_net))

    # ---------------------------------------------------------------- the set up

    def _setup(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        """Rule 21.2 in the order of v1, with the hex of each carrier chosen by the odds.

        A set up zone gives a unit a few hexes, and the hex matters: the one that faces
        the enemy fires, the one at the back hides. A unit takes the hex with the best
        fire at the enemy on the board, less its loss there, plus its cover. A defender
        that sets up first sees no enemy, so it takes the hex that sees the most open
        ground in its range (P21, the engagement area). A leader goes to the squads.
        """
        if not self.v7.setup_by_odds:
            return super()._setup(state, by_action)
        if "place_weapon" in by_action:
            return min(by_action["place_weapon"], key=lambda lc: lc.id).id
        carriers = [lc for lc in by_action.get("place", []) if state.units[lc.command.units[0]].kind != KIND_SW]
        if not carriers:
            if "place_concealment" in by_action:
                return self._conceal(state, by_action)
            return self._first_of(by_action, ("place", "end_setup"))
        # The squads go down before the leaders, so a leader finds its squads.
        unit_id = min((lc.command.units[0] for lc in carriers), key=lambda u: (state.units[u].kind == KIND_LEADER, u))
        options = [lc for lc in carriers if lc.command.units[0] == unit_id]
        unit = state.units[unit_id]
        best: LegalCommand | None = None
        best_key: tuple | None = None
        for lc in options:
            hex_ref = lc.command.hex
            if hex_ref is None:
                continue
            key = (self._setup_value(state, unit, hex_ref), lc.id)
            if best_key is None or key > best_key:
                best, best_key = lc, key
        return best.id if best is not None else min(carriers, key=lambda lc: lc.id).id

    def _setup_value(self, state: State, unit: Unit, hex_ref: HexRef) -> int:
        board = self.engine.board
        cover = self.v6.cover_preference if is_cover(board, hex_ref) else 0
        friends = [u for u in state.infantry_in(hex_ref) if u.player == self.player]
        squads = sum(1 for u in friends if u.kind == "squad")
        leaders = sum(1 for u in friends if u.kind == KIND_LEADER)
        if unit.kind == KIND_LEADER:
            company = squads * 4
        else:
            company = leaders * 2
        stand_in = unit.with_(hex=hex_ref)
        value = cover + company + self._fire_points(state, stand_in, hex_ref) - self._loss(state, unit, hex_ref, False) * self.v7.loss_scale // odds.ONE
        if not self.has_deadline:
            value += self._field_of_fire(hex_ref, unit) * self.v7.field_weight // 4
        return value

    def _field_of_fire(self, hex_ref: HexRef, unit: Unit) -> int:
        """The open ground hexes in the range of the unit with a line of sight from the hex."""
        board = self.engine.board
        reach = self.engine.types[unit.type_key].range
        if reach <= 0:
            return 0
        count = 0
        for other in board.order:
            if other == hex_ref or geometry.distance(hex_ref, other) > reach:
                continue
            if not is_open_ground(board, other):
                continue
            if evaluate_los(board, self.engine.los, hex_ref, other).clear:
                count += 1
        return count

    # ------------------------------------------------------------------ the rout

    def _rout(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        """Rule 13.43: a broken unit routs to the cover where the enemy fire hurts least.

        A broken unit that fails one more check is eliminated, and an agent that reads
        the odds fires at the broken first. So the rout goes to the cover hex with the
        lowest chance of a loss, and to a leader when the chances tie, because the
        leader rallies it (rule 14.3). A unit that may stay does so when its hex is as
        safe as the best rout.
        """
        if not self.v7.rout_by_loss:
            return super()._rout(state, by_action)
        routs = by_action.get("rout", [])
        stays = by_action.get("stay", [])
        if not routs and not stays:
            return self._first_of(by_action, ("end_phase",))
        types = self.engine.types

        def leader_in(hex_ref: HexRef) -> int:
            return min(
                (types[u.type_key].leadership for u in state.infantry_in(hex_ref) if u.player == self.player and u.kind == KIND_LEADER and not u.broken),
                default=1,
            )

        best: LegalCommand | None = None
        best_key: tuple | None = None
        for lc in routs + stays:
            unit = state.units[lc.command.units[0]]
            dst = lc.command.hex if lc.command.action == "rout" else unit.hex
            if dst is None:
                continue
            loss = self._loss(state, unit, dst, False)
            key = (loss, leader_in(dst), self._unit_distance(unit.id, dst), 0 if lc.command.action == "stay" else 1, lc.id)
            if best_key is None or key < best_key:
                best, best_key = lc, key
        return best.id if best is not None else self._first_of(by_action, ("end_phase",))

    # -------------------------------------------------------- the close combat

    def _kill_ways(self, state: State, attackers: tuple[int, ...], targets: tuple[int, ...], leader: int | None) -> int:
        """Rule 20.3: the rolls of 36 that kill, for this attack."""
        types = self.engine.types
        attack = r20_close_combat.firepower(state, types, attackers, attacking=True)
        defense = r20_close_combat.firepower(state, types, targets, attacking=False)
        row = self.engine.tables.cc.odds_row(attack, defense)
        modifier = types[state.units[leader].type_key].leadership if leader is not None else 0
        return sum(count for roll, count in odds.DICE_WAYS.items() if roll + modifier <= row.kill)

    def _assault_odds(self, state: State, ours: tuple[int, ...], theirs: list[Unit]) -> tuple[int, int]:
        """Our kill chance and theirs, out of 36, for a close combat of these units."""
        unbroken = tuple(u.id for u in theirs if not u.broken)
        if not unbroken:
            return odds.WAYS, 0
        our_leader = min(
            (uid for uid in ours if state.units[uid].kind == KIND_LEADER),
            key=lambda uid: self.engine.types[state.units[uid].type_key].leadership,
            default=None,
        )
        their_leader = min(
            (uid for uid in unbroken if state.units[uid].kind == KIND_LEADER),
            key=lambda uid: self.engine.types[state.units[uid].type_key].leadership,
            default=None,
        )
        return self._kill_ways(state, ours, unbroken, our_leader), self._kill_ways(state, unbroken, ours, their_leader)

    def _advance(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        """The v6 advance, with the close combat gate on the odds of rule 20.

        Rule 20.9 eliminates a broken unit in a melee hex, so a hex of broken enemies is a
        sure kill and the advance takes it (P18). A hex with an unbroken enemy is an
        assault, and it is favorable when our kill chance is above theirs by the margin.
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
            ours_kill, theirs_kill = self._assault_odds(state, lc.command.units, enemies)
            favorable = not unbroken or ours_kill * 100 >= theirs_kill * 100 + odds.WAYS * self.v7.close_combat_margin
            if unbroken and not favorable:
                if not self.v6.advance_into_close_combat:
                    continue
                bonus = 0
            else:
                bonus = sum(odds.unit_value(self.engine.types, u) for u in enemies) * ours_kill // odds.WAYS // 2
            bonus += self._rout_block(state, lc.command.units, dst)
            pressed, value = self._step_score(state, unit.id, unit.hex, dst, cache, bonus, len(lc.command.units), moving=False)
            if unbroken and not favorable:
                pressed = 0
            score = (pressed, value, 1 if favorable else 0, -len(unbroken))
            if best_score is None or score > best_score or (score == best_score and best is not None and lc.id < best.id):
                best = lc
                best_score = score
        if best is not None and best_score is not None and (best_score[0] > 0 or best_score[1] > 0):
            return best.id
        return self._first_of(by_action, ("end_phase",))

    def _rout_block(self, state: State, units: tuple[int, ...], dst: HexRef) -> int:
        """P11, the trap: the worth of the broken enemies next to `dst` that have no rout
        route once our units stand there. Rule 13.4 makes a broken unit next to an enemy
        rout, and rule 13.47 eliminates one that cannot reach cover. The core's own test
        (`r13_rout.hopeless`) reads the hypothetical state."""
        if not self.v7.rout_block:
            return 0
        broken = [
            u
            for near in self.engine.board.neighbors(dst)
            for u in state.infantry_in(near)
            if u.player == self.opponent and u.broken
        ]
        if not broken:
            return 0
        moved = {uid: state.units[uid].with_(hex=dst) for uid in units}
        hypothetical = state.with_units(moved)
        worth = 0
        for enemy in broken:
            if r13_rout.hopeless(self.engine.rout_ctx, self.engine.types, hypothetical, enemy):
                worth += odds.unit_value(self.engine.types, enemy) * 2
        return worth * self.v7.fire_weight

    def _close_combat(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        """Rule 20.4: the attack with the best kill chance per attacker, with its leader."""
        attacks = by_action.get("cc_attack", [])
        if not attacks:
            return self._first_of(by_action, ("end_phase",))
        best: LegalCommand | None = None
        best_key: tuple[int, int, str] | None = None
        for lc in attacks:
            extra = dict(lc.command.extra)
            targets = tuple(int(t) for t in extra.get("targets", ()))
            leader = extra.get("leader")
            ways = self._kill_ways(state, lc.command.units, targets, None if leader is None else int(leader))
            worth = ways * sum(odds.unit_value(self.engine.types, state.units[t]) for t in targets)
            key = (worth * 4 // max(1, len(lc.command.units)), worth, lc.id)
            if best_key is None or key > best_key:
                best, best_key = lc, key
        return best.id if best is not None else self._first_of(by_action, ("end_phase",))
