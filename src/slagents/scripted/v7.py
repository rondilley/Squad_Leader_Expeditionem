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

The nation profiles: the American profile leans on fire (a lower floor, a wider group),
and the Soviet profile presses first and accepts the loss. The German profile is the
defence the parameter evolution of 2026-09-20 found, and it holds 95 of 100 against the
v7 Russian where the profile before it held 79 (`NATION_PROFILES`).

The smoke of rule 24 is the sixth place the odds are read (P15, the screen). An assault
engineer squad puts one counter in its hex or next to it, as the first action of its own
Prep Fire Phase. The counter costs the firer the die of rule 24.6 on each line of sight
that goes into, out of, or through the hex, so it is worth what it takes off the loss of
the units it screens, less the fire it takes off the units that shoot across it.

Agent v7 measures both with the odds: for each hex the host offers, the fall of the
expected loss of its own force, and the fall of its own expected fire. It keeps the
best, and it keeps nothing when the best is below `smoke_floor`. The loss model reads
the smoke on the board too, so a unit that stands behind a screen knows it (`odds.loss`
with `group_meets_smoke`).

Slice 7 (2026-09-24, docs/reports/2026-09-24_v7_strength.md) added five features, each
behind a parameter, and measured each one as the Russian attacker of scenario 1 against a
panel of three German records on paired seeds:

1. `mass`: two targets and one spare, and each group goes in one Movement Phase. Off: it
   lost on the measure.
2. `advance_take` with `open_moves` false: no step of a move and no advance ends in open
   ground that an enemy sees, a hex next to the target that no enemy sees earns a bonus,
   and the Advance Phase takes the target. On: the German Prep Fire Phase killed more
   Russian squads that stood in the open than any other cause.
3. `rally_points`: a rally leader for each group, a rout to it, and a stay only out of
   sight. Off: it lost on the measure.
4. `lookahead`: the core applies the best K moves to the player state. Off: no gain.
5. `search_iterations`: a tree search over the macro of each own player turn, with
   rollouts on the player state. Off by default for its cost; the report has its measure.

What v7 does not do yet: it has no reserve (P19). Its vehicles drive and fire with the
armor policy of `armor.py` (2026-10-10), and since the combined-arms pass (2026-10-11, v7.1)
the parameters of that policy are v7 parameters (`tank_*`), so the evolution searches them,
and its squads escort the tanks (`escort_bonus`, P13).
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
from slcore.rules import r05_movement, r08_fire, r10_resolution, r13_rout, r20_close_combat, r22_flamethrower, r23_demolition
from slcore.rules.r11_terrain import is_open_ground
from slcore.rules.r13_rout import is_cover
from slcore.units import KIND_LEADER, KIND_SW, Unit
from slcore.view import visible_to
from typing import Any

from slagents.scripted import odds
from slagents.scripted.armor import ArmorParameters, ArmorPolicy
from slagents.scripted.v6 import ENEMY_HEX_HALVES, POSITIONAL_KINDS
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
# The penalty of a step that `mass` holds back until the group goes. It is larger than
# any gain a step can earn, and a stand costs nothing, so the unit stays.
MASS_HOLD = 1_000_000


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
    smoke_floor: int = 5  # percent of a squad break a smoke counter has to save, or it is not placed
    smoke_fire_share: int = 50  # percent of the fire it costs that counts against a smoke counter
    smoke_horizon: int = 2  # turns of the route a screen is measured over, for the hexes it covers
    # Slice 7 of the 2026-09-24 plan. Each one is off by default, so a record without it
    # plays as before, and the measurement compares each one on and off.
    mass: bool = False  # step 1: two targets and one spare, and each group goes in one turn
    stage_loss: int = 10  # percent: before its group goes, a unit steps into no hex with a loss chance above this
    spare_share: int = 50  # percent of a full share of the force that the spare target takes
    advance_take: bool = True  # step 2: close up where the defender does not see, then take the building in the Advance Phase
    hidden_bonus: int = 6  # score points of a hex next to the target that no enemy sees
    take_bonus: int = 24  # score points of an advance into a hex of the target building
    open_moves: bool = False  # with advance_take, false keeps each step of a move out of open ground an enemy sees
    rally_points: bool = False  # step 3: a leader in cover out of sight for each group, and the rout goes to it
    sight_range: int = 16  # hexes: an enemy unit further away than this does not count as one that sees a hex
    lookahead: int = 0  # step 4: the best K moves (and K fire plans) are compared one ply deep; zero is off
    search_iterations: int = 0  # step 5: rollouts of the tree search over the plan of each Movement Phase; zero is off
    search_seed: int = 1  # the dice of the rollouts come from this seed, the turn, and the rollout
    search_commands: int = 600  # the most commands one rollout plays
    # The engineer tools of rules 22, 23, and 27 (`slagents.scripted.engineer`, 2026-09-24).
    engineer: bool = True  # the flamethrower, the demolition charge, and the sewer; false plays as before
    sewer_gain: int = 3  # hexes nearer its target that a sewer exit must be, or the stack stays up
    tool_weight: int = 0  # score points of one half of expected enemy loss from a charge or a flamethrower in reach of a move; zero is off, because 2 lost on the measure
    # The combined-arms pass (2026-10-11, RV-9 P4, P6, P7, P13). The names are those of
    # `armor.ArmorParameters` with `tank_` in front; `armor_parameters` maps them.
    escort_bonus: int = 6  # score points of a squad's step next to a tank of ours in contact with no escort
    tank_standoff: int = 4  # hexes a tank keeps from enemy infantry
    tank_escort: bool = True  # P13: the tanks stay with the infantry, and a screened tank may close in
    tank_leash: int = 3  # hexes from the own infantry a firing position may be at no cost
    tank_leash_cost: int = 4  # movement halves for each hex past the leash
    tank_escorted_standoff: int = 2  # hexes a screened tank keeps from enemy infantry
    tank_danger_cost: int = 8  # movement halves of a route hex in enemy AT range with no escort
    tank_bound: bool = True  # P7: bounding overwatch in contact
    tank_contact_range: int = 12  # hexes: an enemy this near a tank puts it in contact
    tank_overwatch_range: int = 8  # hexes a bounding tank may be from the tank that watches it
    tank_section_fire: bool = True  # P6: the tanks fire as a section
    tank_focus_bonus: int = 4  # a hex a tank of ours fired at in this phase
    tank_threat_bonus: int = 3  # a hex with an enemy anti-tank weapon
    tank_support_bonus: int = 3  # a hex near the own infantry
    tank_flank_bonus: int = 8  # movement halves off a position that sees an enemy side or rear
    tank_gun_exposure: int = 6  # movement halves on a position for each enemy gun that sees it
    tank_hold_margin: int = 4  # movement halves another position must gain before a tank leaves its own


# The record of a nation on the attack: a side with a positional victory condition of
# its own has a deadline and has to cross ground to reach it.
NATION_PROFILES: dict[str, Parameters] = {
    "german": Parameters(aggression=3, cover_preference=3, threat_aversion=1, superiority_tenths=13, schedule_margin=2, close_combat_margin=0),
    "soviet": Parameters(aggression=3, cover_preference=2, threat_aversion=1, superiority_tenths=12, suppression_priority=1, schedule_margin=3, loss_scale=9),
    "american": Parameters(aggression=2, cover_preference=4, fire_priority=3, threat_aversion=2, superiority_tenths=18, suppression_priority=3, schedule_margin=1, fire_floor=3, group_size=7),
}


# The record of a nation on the defence, where a nation has one. The German record is
# the result of the parameter evolution of 2026-09-20 (`runs/20260920T201936Z-evolve-v7`,
# candidate 167): 30 generations of the defence of scenario 1 against the v7 Russian,
# and then 100 games on seeds no generation played. It holds 95 of 100 where the record
# before it held 79, and two other candidates of the same run held 91 and 92.
#
# What the numbers say as doctrine. The defender fires only when the shot is worth
# something (`fire_floor` 4) and it does not value a hex for the fire it gives
# (`fire_weight` 0), because it sits in the buildings the scenario gave it. It counts a
# threat in large units (`threat_scale` 16) and it does not keep away from a threatened
# hex (`threat_aversion` 0), because the enemy fires at each hex of its line. It puts a
# high price on a loss (`loss_scale` 30), it keeps its groups small and without overkill
# (`group_size` 4, `overkill_share` 1), and it holds what it has (`spare_targets` 1,
# `garrison_hexes` 3, `field_weight` 4).
#
# The record is a record of the defence and of no other role. As the German attacker of
# scenario 2 it wins 6 of 100 where the attack record wins 23, so the role picks the
# record (`profile_for`, `side_defends`).
DEFENCE_PROFILES: dict[str, Parameters] = {
    "german": Parameters(
        aggression=4,
        cover_preference=5,
        fire_priority=6,
        group_size=4,
        threat_aversion=0,
        superiority_tenths=10,
        threat_scale=16,
        fire_floor=4,
        fire_weight=0,
        overkill_share=1,
        loss_scale=30,
        return_margin=6,
        close_combat_margin=-3,
        urgency_cap=10,
        suicide_percent=67,
        spare_targets=1,
        garrison_hexes=3,
        share_targets=1,
        field_weight=4,
        rout_block=False,
        rout_by_loss=False,
        # The evolution found this record before slice 7, so it keeps the play it was
        # measured with: no Advance Phase rule of step 2.
        advance_take=False,
        open_moves=True,
    ),
}


class UnknownNation(Exception):
    """The nation profile is not defined. British waits for its research pass."""


def profile_for(nation: str, defending: bool = False) -> Parameters:
    """The record of a nation in a role. A nation with no record of the defence keeps
    its record of the attack, because a record of one role is better than none."""
    key = nation.strip().lower()
    if key not in NATION_PROFILES:
        raise UnknownNation(
            f"no v7 profile for {nation!r}. Defined: {', '.join(sorted(NATION_PROFILES))}. "
            f"British is not confirmed yet and waits for a follow-up research pass."
        )
    if defending and key in DEFENCE_PROFILES:
        return DEFENCE_PROFILES[key]
    return NATION_PROFILES[key]


def side_defends(engine: Any, player: int) -> bool:
    """True when this side has no positional victory condition of its own.

    A side with one has a deadline and has to cross ground to reach it, which is the
    attack. The other side holds what it has, which is the defence. It is the same test
    the schedule of v6 uses (`_side_has_deadline`), so the record and the schedule read
    the scenario the same way.
    """
    side = engine.scenario.players()[player]
    for condition in engine.scenario.victory:
        if condition.kind in POSITIONAL_KINDS and str(dict(condition.params).get("side", "")) == side:
            return False
    return True


def with_parameters(**changes: object) -> Parameters:
    return replace(Parameters(), **changes)


def parameters_of_name(name: str, defending: bool = False) -> Parameters:
    """The record an agent name asks for: `v7`, `v7:<nation>`, `v7[...]`, or
    `v7:<nation>[...]`.

    The last form is a nation record with a few values of its own, which a study of one
    rule on a record asks for (`v7:german[smoke_horizon=1]`). With `defending` a nation
    name gives the record of the defence, where the nation has one.
    """
    if not name.startswith("v7"):
        raise ValueError(f"not a v7 agent name: {name!r}")
    rest = name[2:]
    changes = ""
    if rest.endswith("]") and "[" in rest:
        rest, changes = rest[: rest.index("[")], rest[rest.index("[") + 1 : -1]
    base = Parameters() if not rest else profile_for(rest[1:] if rest.startswith(":") else rest, defending)
    return parameters_from_text(changes, base) if changes else base


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


def v6_parameters(p: Parameters) -> V6Parameters:
    """The v6 part of a v7 record."""
    return V6Parameters(
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
        escort_bonus=p.escort_bonus,
    )


def armor_parameters(p: Parameters) -> ArmorParameters:
    """The armor policy part of a v7 record."""
    return ArmorParameters(
        standoff=p.tank_standoff,
        escort=p.tank_escort,
        leash=p.tank_leash,
        leash_cost=p.tank_leash_cost,
        escorted_standoff=p.tank_escorted_standoff,
        danger_cost=p.tank_danger_cost,
        bound=p.tank_bound,
        contact_range=p.tank_contact_range,
        overwatch_range=p.tank_overwatch_range,
        section_fire=p.tank_section_fire,
        focus_bonus=p.tank_focus_bonus,
        threat_bonus=p.tank_threat_bonus,
        support_bonus=p.tank_support_bonus,
        flank_bonus=p.tank_flank_bonus,
        gun_exposure=p.tank_gun_exposure,
        hold_margin=p.tank_hold_margin,
    )


@dataclass(frozen=True)
class Plan:
    """A fire plan for one target: the members in the order they join, and its worth."""

    target: HexRef
    members: tuple[LegalCommand, ...]
    value: int  # the worth, with the lift for a target that covers our force
    raw: int  # the expected loss of the enemy alone


class ScriptedV7(ScriptedV6):
    name = "scripted"
    # 7.1 (2026-10-11): the combined-arms pass of the armor policy, with its parameters.
    version = "7.1"

    def __init__(self, engine: Engine, player: int, params: Parameters | None = None) -> None:
        self.v7 = params or Parameters()
        super().__init__(engine, player, v6_parameters(self.v7))
        self.armor = ArmorPolicy(engine, player, armor_parameters(self.v7), objectives=lambda: self.open_objectives or self.objectives)
        self.engineer_on = self.v7.engineer
        self.sewer_gain = self.v7.sewer_gain
        # The expected loss of a unit in each hex, and the fire a unit gives from each hex,
        # for this enemy picture.
        self._loss_map: dict[tuple, int] = {}
        self._fire_map: dict[tuple, int] = {}
        # The odds of a charge or a flamethrower at each enemy hex, for this enemy picture.
        self._tool_map: dict[tuple, int] = {}
        # The movement halves along the path of each route field, by field.
        self._moves_along: dict[tuple[tuple[HexRef, ...], bool], dict[HexRef, int]] = {}
        # The exposure of each of our units for the decision in hand.
        self._exposure_key: tuple = ()
        self._exposure_now: dict[int, int] = {}
        # The hexes a seen enemy unit sees, for this enemy picture (`advance_take`, `rally_points`).
        self._sight: dict[HexRef, bool] = {}
        # The rally leader of each group, and the group of each rally leader (`rally_points`).
        self.rally_leaders: dict[tuple[HexRef, ...], int] = {}
        self._rally_group: dict[int, tuple[HexRef, ...]] = {}
        # The tree search (step 5): the record the agent was built with, the macro of the
        # player turn in hand, and the turn it holds for.
        self._base_v7 = self.v7
        self._macro_turn: tuple[int, int] | None = None
        self.macro_log: list[tuple[int, str]] = []
        # The own legal list of the state in hand, for the lookahead (step 4).
        self._own_frame_key: int = -1
        self._own_frame: DecisionFrame | None = None
        # The press of each group of the plan, for the decision in hand (`mass`).
        self._group_key: tuple = ()
        self._group_level: dict[tuple[HexRef, ...], int] = {}

    def select(self, state: State, frame: DecisionFrame) -> str:
        """The smoke window of rule 24.3 comes first, and the rest goes to v6.

        With `search_iterations` the first decision of each own Movement Phase runs the
        tree search, and the macro it picks holds for the rest of the player turn.
        """
        self._search_window(state, frame)
        if frame.sub_step == "smoke_window":
            by_action: dict[str, list[LegalCommand]] = {}
            for lc in frame.commands:
                by_action.setdefault(lc.command.action, []).append(lc)
            if by_action.get("place_smoke"):
                self._refresh_routes(state)
                self._refresh_objectives(state)
                return self._smoke(state, by_action)
        return super().select(state, frame)

    # ------------------------------------------------------------------ the plan

    def _targets_wanted(self) -> int:
        """The places the plan takes at one time: the swing margin plus the spare.

        v6 takes one past the margin, so a building lost cancels nothing. With five turns
        and a garrison in each building, the force that divides three ways takes none in
        time. `spare_targets` sets the spare, and zero puts the whole force on the margin
        (P5, mass against the weak part).
        """
        wanted = super()._targets_wanted()
        if wanted <= 0 or self.v7.mass:
            # Mass (P5): the margin of the swing and one spare, as v6 takes. With a margin of
            # two that is two targets and a spare, and not four targets in parallel.
            return wanted
        return max(1, wanted - 1 + self.v7.spare_targets)

    def _refresh_objectives(self, state: State) -> None:
        """The v6 plan, and with `rally_points` one rally leader for each group."""
        super()._refresh_objectives(state)
        if not self.v7.rally_points or not self.has_deadline:
            self.rally_leaders = {}
            self._rally_group = {}
            return
        leaders = [
            u
            for u in state.player_units(self.player)
            if u.kind == KIND_LEADER and not u.broken and u.hex is not None and u.carrier is None
        ]
        groups = sorted({t for t in self.assignment.values() if t and t != ()}, key=lambda t: t)
        chosen: dict[tuple[HexRef, ...], int] = {}
        # A leader keeps its group while it lives, so the rally point does not jump.
        for target, uid in self.rally_leaders.items():
            if target in groups and any(u.id == uid for u in leaders):
                chosen[target] = uid
        taken = set(chosen.values())
        # Half the leaders at most stand back as rally points, and the weakest of them: a
        # leader with a good rating lifts the fire and the morale of the assault (rule 15).
        limit = max(1, len(leaders) // 2)
        types = self.engine.types
        for target in groups:
            if target in chosen:
                continue
            if len(chosen) >= limit:
                break
            members = [u for u in state.player_units(self.player) if u.hex is not None and self.assignment.get(u.id) == target and u.kind != KIND_LEADER]
            if not members:
                continue
            free = [u for u in leaders if u.id not in taken]
            if not free:
                break
            best = min(
                free,
                key=lambda u: (-types[u.type_key].leadership, min(geometry.distance(u.hex, m.hex) for m in members), u.id),
            )
            chosen[target] = best.id
            taken.add(best.id)
        self.rally_leaders = chosen
        self._rally_group = {uid: target for target, uid in chosen.items()}

    def _rally_value(self, state: State, unit: Unit, hex_ref: HexRef) -> int:
        """The worth of a hex as the rally point of a group (rules 14.3 and 13.43).

        The hex is out of every enemy line of sight, in cover when it can be, and near the
        units of the group, so a broken unit reaches it in one rout.
        """
        target = self._rally_group.get(unit.id, ())
        members = [
            u.hex
            for u in state.player_units(self.player)
            if u.hex is not None and u.id != unit.id and self.assignment.get(u.id) == target and u.kind != KIND_LEADER
        ]
        near = min((geometry.distance(hex_ref, m) for m in members), default=0)
        value = self.v6.cover_preference if is_cover(self.engine.board, hex_ref) else 0
        value -= near * self.v6.aggression
        if self._seen_by_enemy(state, hex_ref):
            value -= MASS_HOLD
        return value

    def _target_rooms(self, targets: list[tuple[str, tuple[HexRef, ...]]], free: int) -> dict[str, int]:
        """With `mass` the spare target takes `spare_share` of a share and the main targets
        take the rest. The spare is the last target of the order, the far or the strong one."""
        if not self.v7.mass or len(targets) < 3:
            return super()._target_rooms(targets, free)
        share = (free + len(targets) - 1) // len(targets)
        spare = max(1, (share * self.v7.spare_share + 99) // 100)
        main = len(targets) - 1
        each = (max(0, free - spare) + main - 1) // main
        rooms = {place_id: each for place_id, _ in targets[:-1]}
        rooms[targets[-1][0]] = spare
        return rooms

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
            self._tool_map = {}
            self._moves_along = {}
            self._sight = {}

    def _seen_enemies(self, state: State) -> list[Unit]:
        """The enemy units this player can see. A hidden or concealed unit is not one of them."""
        return [u for u in state.player_units(self.opponent) if visible_to(state, u, self.player)]

    def _seen_by_enemy(self, state: State, hex_ref: HexRef) -> bool:
        """True when an unbroken enemy unit this player sees has a clear line of sight to
        the hex, inside `sight_range`. A hex with no such unit is dead ground (rule 7)."""
        found = self._sight.get(hex_ref)
        if found is not None:
            return found
        board = self.engine.board
        seen = False
        for enemy in self._seen_enemies(state):
            if enemy.hex is None or enemy.broken or enemy.kind == KIND_SW:
                continue
            if geometry.distance(enemy.hex, hex_ref) > self.v7.sight_range:
                continue
            if enemy.hex == hex_ref or evaluate_los(board, self.engine.los, enemy.hex, hex_ref).clear:
                seen = True
                break
        self._sight[hex_ref] = seen
        return seen

    def _enemy_groups(self, state: State, dst: HexRef) -> list[odds.EnemyGroup]:
        """The fire groups the enemy could form against a hex, from the units this player sees."""
        return odds.enemy_groups(self.engine, state, dst, self._seen_enemies(state))

    def _loss(self, state: State, unit: Unit, dst: HexRef, moving: bool) -> int:
        """The chance, out of `odds.ONE`, that this unit breaks or dies in `dst` under the
        fire of each enemy group that sees the hex (`odds.loss`), held by hex, phase, and
        unit type, because a decision asks the same hex many times."""
        key = (dst, moving, unit.type_key, unit.broken, unit.berserk, unit.hidden)
        found = self._loss_map.get(key)
        if found is not None:
            return found
        groups = self._enemy_groups(state, dst)
        chance = odds.loss(self.engine, state, unit, dst, moving, groups) if groups else 0
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
            group = FireGroup(target, tuple(members), None)
            value = odds.shot(self.engine, hypothetical, group, PHASE_PREP_FIRE, smoke=odds.group_meets_smoke(self.engine, hypothetical, group)).value
            if value > best:
                best = value
        self._fire_map[key] = best
        return best

    def _fire_points(self, state: State, unit: Unit, dst: HexRef) -> int:
        """The fire a position gives, in score points. A lift for the friends next to the
        position (mass, P5) was measured and lost: the squads bunched in one hex, and
        one KIA result took the stack."""
        return self._fire_value(state, unit, dst) * self.v7.fire_weight // odds.ONE

    def _tool_points(self, state: State, unit: Unit, dst: HexRef, moving: bool) -> int:
        """The worth of a step or a stand for a charge or a flamethrower, in score points.

        A carrier that ends its Movement Phase next to an enemy hex places its charge
        there, and a flamethrower in range fires in the Advancing Fire Phase (rules 22
        and 23). Each happens only when the carrier holds its end hex through the
        Defensive Fire Phase (rule 23.3), so the expected enemy loss of the best tool shot
        counts times the chance that the carrier does not break in that hex.

        The move is chosen one step at a time. A step counts the best end hex that the
        unit still reaches in this phase from `dst`, and a stand counts its own hex only.
        So the step from three hexes to two carries the value of the charge, and a stand
        at three hexes does not. Before this the carriers held at the range of their own
        fire: at the start of a German Movement Phase of scenario 2, 350 of 461 carrier
        positions were three or four hexes from the nearest enemy hex, and 10 were one or
        two. Of 36 charges placed in 36 games, 21 did not explode, because the placer
        broke (2026-09-25).
        """
        if not self.engineer_on or self.v7.tool_weight <= 0 or state.phase != PHASE_MOVEMENT or unit.broken:
            return 0
        if unit.hex is None:
            return 0
        types = self.engine.types
        charges = [w for w in state.carried_by(unit.id) if r23_demolition.can_place(state, types, unit, w)]
        flames = [
            w
            for w in state.carried_by(unit.id)
            if r22_flamethrower.is_flamethrower(types, w) and not w.broken and not w.malfunction and not w.eliminated
        ]
        if flames and (unit.kind == KIND_LEADER or not r22_flamethrower.may_operate(types, unit)):
            flames = []
        if not charges and not flames:
            return 0
        ends = [dst]
        if moving:
            left = types[unit.type_key].mf_halves - unit.mf_used
            if dst != unit.hex:
                cost, _ = r05_movement.entry_cost_halves(self.engine.move_ctx, unit.hex, dst)
                left -= cost if cost is not None else left
            ends = self._reach(state, dst, left)
        targets = self._tool_targets(state)
        own = {u.hex for u in state.player_units(self.player) if u.hex is not None and u.id != unit.id}
        best = 0
        for end in ends:
            shot = 0
            for target in targets:
                if target == end:
                    continue
                if charges and target not in own and geometry.distance(end, target) == 1:
                    shot = max(shot, self._tool_odds(state, "charge", charges[0], target))
                if flames and r22_flamethrower.in_range(types, flames[0], end, target):
                    if evaluate_los(self.engine.board, self.engine.los, end, target).clear:
                        shot = max(shot, self._tool_odds(state, "flame", flames[0], target))
            if shot > 0:
                hold = odds.ONE - self._loss(state, unit, end, end != unit.hex or unit.moved)
                best = max(best, shot * hold // odds.ONE)
        return best * self.v7.tool_weight // odds.ONE

    def _reach(self, state: State, start: HexRef, halves: int) -> list[HexRef]:
        """The hexes a unit in `start` enters with `halves` of movement left, and `start`.

        No hex with an enemy unit or counter this player sees is entered (rule 5.7)."""
        blocked = set(self._tool_targets(state))
        ctx = self.engine.move_ctx
        board = self.engine.board
        best: dict[HexRef, int] = {start: 0}
        heap: list[tuple[int, HexRef]] = [(0, start)]
        while heap:
            spent, here = heapq.heappop(heap)
            if spent > best.get(here, spent):
                continue
            for nxt in board.neighbors(here):
                if nxt in blocked:
                    continue
                cost, _ = r05_movement.entry_cost_halves(ctx, here, nxt)
                if cost is None or spent + cost > halves:
                    continue
                if spent + cost < best.get(nxt, halves + 1):
                    best[nxt] = spent + cost
                    heapq.heappush(heap, (spent + cost, nxt))
        return sorted(best)

    def _tool_targets(self, state: State) -> list[HexRef]:
        """The enemy hexes this player sees: a hex with an enemy unit or an enemy counter."""
        counters = {c.hex for c in state.concealment if c.player != self.player and c.hex is not None}
        return sorted(set(r10_resolution.enemy_occupied_hexes(state, self.player)) | counters)

    def _tool_odds(self, state: State, kind: str, weapon: Unit, target: HexRef) -> int:
        """The expected enemy loss of one tool shot at `target`, held for the enemy picture.

        A hex with a concealment counter and no enemy unit the player sees is worth the
        shot at half firepower (rules 22.1 and 23.5) against one stand-in: an unbroken
        squad of the enemy type this player sees most. The agent does not read what is
        below the counter, and a dummy counter (rule 25.7) is worth the same stand-in.
        """
        key = (kind, weapon.type_key, target)
        found = self._tool_map.get(key)
        if found is not None:
            return found
        hypothetical = state
        halved = False
        seen = [u for u in state.infantry_in(target) if u.player != self.player and visible_to(state, u, self.player)]
        if not seen:
            stand_in = self._enemy_stand_in(state)
            if stand_in is None:
                self._tool_map[key] = 0
                return 0
            # The counter comes off in the hypothetical state, so the odds see the stand-in,
            # and `halved` puts the halving of the counter back.
            hypothetical = state.with_(concealment=tuple(c for c in state.concealment if c.hex != target))
            hypothetical = hypothetical.with_unit(
                stand_in.with_(hex=target, moved=False, broken=False, eliminated=False, hidden=False, carrier=None)
            )
            halved = True
        if kind == "charge":
            value = odds.charge(self.engine, hypothetical, self.player, weapon.type_key, target, halved=halved).value
        else:
            value = odds.flame(self.engine, hypothetical, self.player, weapon, target, halved=halved).value
        self._tool_map[key] = value
        return value

    def _enemy_stand_in(self, state: State) -> Unit | None:
        """An enemy squad of the type most common in the enemy order of battle, or None.

        The scenario card prints the order of battle, so the player state keeps each
        enemy unit with its type and no place (`slcore.player_state`). The count reads
        the type only.
        """
        counts: dict[str, int] = {}
        first: dict[str, Unit] = {}
        for u in state.player_units(self.opponent):
            if u.kind == "squad":
                counts[u.type_key] = counts.get(u.type_key, 0) + 1
                first.setdefault(u.type_key, u)
        if not counts:
            return None
        return first[max(sorted(counts), key=lambda k: counts[k])]

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
        enemy_hexes = {u.hex for u in self._seen_enemies(state) if u.hex is not None and not u.broken and u.is_infantry}
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
        """The press of the unit, or with `mass` the press of its whole group.

        A group is the units the plan sends to one target. With `mass` the group goes when
        its slowest unit has to go, so the units cross the open in one Movement Phase and
        the defender's groups have more targets than shots (P5). Until then each unit
        closes up in the hexes the defender does not hit (`stage_loss`).
        """
        own = self._unit_press_level(state, unit_id, unit_hex)
        if not self.v7.mass or own == 2 or not self.has_deadline:
            return own
        return max(own, self._group_levels(state).get(self.assignment.get(unit_id, ()), 0))

    def _group_members(self, state: State, target: tuple[HexRef, ...]) -> list[Unit]:
        """The unbroken squads of this side that the plan sends to this target."""
        return [
            u
            for u in state.player_units(self.player)
            if u.hex is not None
            and not u.broken
            and u.kind != KIND_LEADER
            and u.is_infantry
            and self.assignment.get(u.id) == target
            and u.hex not in target
        ]

    def _group_levels(self, state: State) -> dict[tuple[HexRef, ...], int]:
        """The press of each group: the highest press of a unit of the group, for this decision."""
        key = (state.seq, state.phase, tuple(sorted(self.assignment.items())))
        if self._group_key == key:
            return self._group_level
        levels: dict[tuple[HexRef, ...], int] = {}
        for target in set(self.assignment.values()):
            level = 0
            for u in self._group_members(state, target):
                level = max(level, self._unit_press_level(state, u.id, u.hex))
                if level == 2:
                    break
            levels[target] = level
        self._group_key = key
        self._group_level = levels
        return levels

    def _unit_press_level(self, state: State, unit_id: int, unit_hex: HexRef) -> int:
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
        if unit_id in self._rally_group:
            # A rally leader goes where the rally point is best, and nowhere else.
            return (0, self._rally_value(state, state.units[unit_id], dst))
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
        hold = 0
        if self.v7.mass and moving and self.has_deadline and state.phase == PHASE_MOVEMENT:
            exposure, hold = self._mass_exposure(state, unit, dst, exposure, level)
        penalty = exposure * self.v7.loss_scale * max(1, count) // odds.ONE
        fire = self._fire_points(state, unit, dst) + self._tool_points(state, unit, dst, moving)
        if self.v7.advance_take and moving and target and dst not in target:
            bonus += self._hidden_approach(state, dst, target)
            if (
                not self.v7.open_moves
                and state.phase == PHASE_MOVEMENT
                and not is_cover(self.engine.board, dst)
                and self._seen_by_enemy(state, dst)
            ):
                # Rule 16.5: a unit that moves in the open in the sight of the defender is
                # fired at with a minus two. Only a run that reaches the target stays forced.
                bonus -= MASS_HOLD
        # Tempo (P17): a turn with no progress is a turn lost. The worth of a hex of
        # progress grows as the slack shrinks, so the attacker moves through low loss
        # early and accepts more loss late, in place of a wait and then a rush.
        urgency = self._urgency(state, unit_id, unit_hex)
        bonus += self._escort_value(state, unit, dst)
        value = gain * self.v6.aggression * urgency + cover + fire + bonus - penalty * self.v6.threat_aversion - hold
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

    def _hidden_approach(self, state: State, dst: HexRef, target: tuple[HexRef, ...]) -> int:
        """The worth of a hex next to the target that no enemy sees (`advance_take`).

        A unit that ends its move there draws no defensive fire (rule 16.1 needs a line of
        sight) and it advances into the target in the Advance Phase (rule 4.7)."""
        if not any(geometry.distance(dst, t) == 1 for t in target):
            return 0
        if self._seen_by_enemy(state, dst):
            return 0
        return self.v7.hidden_bonus

    def _mass_exposure(self, state: State, unit: Unit, dst: HexRef, exposure: int, level: int) -> tuple[int, int]:
        """The exposure of a move with `mass`, and the hold penalty.

        Before its group goes, a step into a hex with a loss chance above `stage_loss` is
        held back with a penalty larger than any gain. When the group goes, each enemy
        group fires one time, so the loss of one mover is its share: the enemy groups
        that see the hex, over the movers of the group.
        """
        if level < 2:
            if exposure * 100 > odds.ONE * self.v7.stage_loss:
                return exposure, MASS_HOLD
            return exposure, 0
        if not is_cover(self.engine.board, dst):
            # A KIA result of rule 8.8 takes the whole stack, so the wave goes in one unit to
            # a hex of open ground, and a second unit that joins it pays for both.
            friends = sum(1 for u in state.infantry_in(dst) if u.player == self.player and not u.broken)
            if friends:
                return exposure, exposure * self.v7.loss_scale * friends // odds.ONE
        movers = len(self._group_members(state, self.assignment.get(unit.id, ())))
        groups = len(self._enemy_groups(state, dst)) * max(1, self.v7.share_targets)
        if exposure > 0 and groups > 0 and movers > groups:
            exposure = exposure * groups // movers
        return exposure, 0

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
        theirs = sum(1 for u in self._seen_enemies(state) if u.kind == "squad" and not u.broken and u.hex is not None)
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
        if unit_id in self._rally_group:
            return self._rally_value(state, unit, unit.hex)
        cover = self.v6.cover_preference if is_cover(self.engine.board, unit.hex) else 0
        # One unit decides for itself: the others of the stack make their own choice, and
        # a stand that pays for the whole stack sends each unit out into the open alone.
        fire = self._fire_points(state, unit, unit.hex) + self._tool_points(state, unit, unit.hex, False)
        escort = self._escort_value(state, unit, unit.hex)
        return cover + fire + escort - self._penalty(state, unit, unit.hex, False, 1) * self.v6.threat_aversion

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
        if phase == PHASE_PREP_FIRE and self.has_deadline and self.v7.lookahead > 0:
            chosen = self._prep_lookahead(state, by_action, phase)
            return chosen if chosen is not None else self._first_of(by_action, ("end_phase",))
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
                trial_value = odds.shot(self.engine, state, trial, phase, smoke=odds.group_meets_smoke(self.engine, state, trial)).value
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
        current = odds.shot(self.engine, state, group, phase, smoke=odds.group_meets_smoke(self.engine, state, group)).value
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
                trial_value = odds.shot(self.engine, state, trial, phase, smoke=odds.group_meets_smoke(self.engine, state, trial)).value
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
                trial_group = FireGroup(target, tuple(members + [member]), None)
                trial_value = odds.shot(self.engine, state, trial_group, PHASE_DEFENSIVE_FIRE, smoke=odds.group_meets_smoke(self.engine, state, trial_group)).value
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

    # ----------------------------------------------------------------- rule 24

    def _screened_units(self, state: State) -> list[tuple[int, int, tuple[HexRef, ...]]]:
        """Each of our units a screen could cover: its worth and the hexes it needs.

        The hexes of a unit are the hex it stands in and the hexes of its route that it
        reaches inside `smoke_horizon` turns. A unit that has to cross open ground is
        the unit a screen is for (P15). The list is by unit and not by hex, so a screen
        over a whole route saves that unit one time and not one time for each hex.
        """
        types = self.engine.types
        out: list[tuple[int, int, tuple[HexRef, ...]]] = []
        allowance = self.v7.smoke_horizon
        for unit in state.player_units(self.player):
            if unit.hex is None or unit.broken or unit.is_vehicle or unit.kind == KIND_SW:
                continue
            hexes = {unit.hex}
            target = self.assignment.get(unit.id, self.open_objectives)
            if target:
                field = self._route_field(state, target, safe=True)
                here = field.get(unit.hex)
                if here is not None:
                    reach = allowance * max(1, types[unit.type_key].mf_halves)
                    for hex_ref, cost in field.items():
                        if cost < here and here - cost <= reach:
                            hexes.add(hex_ref)
            out.append((unit.id, odds.unit_value(types, unit), tuple(sorted(hexes))))
        return out

    def _loss_under(self, state: State, hex_ref: HexRef, moving: bool) -> int:
        """The chance a squad of ours breaks in this hex, under the state as it stands.

        The reference unit of the side stands in for the squad, as the route field does,
        so one number covers the hex and not each unit of the force.
        """
        reference = self._reference_unit(state)
        if reference is None:
            return 0
        groups = self._enemy_groups(state, hex_ref)
        if not groups:
            return 0
        return odds.loss(self.engine, state, reference, hex_ref, moving, groups)

    def _smoke(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        """Rule 24.3: the counter goes where it takes the most loss off our force.

        The value of a counter is what it saves: for each of our units, the best fall of
        the expected loss over the hexes that unit needs, times the worth of the unit.
        Against it stands a share of the fire we lose across the screen. A counter that
        saves less than `smoke_floor` of a squad is not placed, because a side has a few
        counters in a game (rule 24.1) and a later turn may want one.
        """
        from slcore.game import Smoke

        screened = self._screened_units(state)
        if not screened:
            return self._first_of(by_action, ("end_phase",))
        wanted = sorted({h for _uid, _worth, hexes in screened for h in hexes})
        before_loss = {h: self._loss_under(state, h, True) for h in wanted}
        best: LegalCommand | None = None
        best_value = SQUAD * self.v7.smoke_floor // 100
        for lc in sorted(by_action["place_smoke"], key=lambda c: c.id):
            hex_ref = lc.command.hex
            if hex_ref is None:
                continue
            hypothetical = state.with_(smoke=state.smoke + (Smoke(hex_ref, self.player),))
            self._loss_map = {}
            after_loss = {h: self._loss_under(hypothetical, h, True) for h in wanted}
            gain = 0
            for _uid, worth, hexes in screened:
                fall = max(before_loss[h] - after_loss[h] for h in hexes)
                if fall > 0:
                    gain += fall * worth
            # The screen costs us the fire that crosses it. The share is a parameter,
            # because a unit that cannot fire this turn loses nothing by the smoke.
            cost = 0
            for unit in state.player_units(self.player):
                if unit.hex is None or unit.broken or unit.kind == KIND_LEADER or unit.is_vehicle:
                    continue
                self._fire_map = {}
                without = self._fire_value(state, unit, unit.hex)
                self._fire_map = {}
                with_smoke = self._fire_value(hypothetical, unit, unit.hex)
                if without > with_smoke:
                    cost += (without - with_smoke) * self.v7.smoke_fire_share // 100
            value = gain - cost
            if value > best_value:
                best, best_value = lc, value
        self._loss_map = {}
        self._fire_map = {}
        if best is None:
            return self._first_of(by_action, ("end_phase",))
        return best.id

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
        if self.v7.rally_points:
            return self._rout_to_rally(state, routs, stays, by_action)
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

    def _rout_to_rally(self, state: State, routs: list[LegalCommand], stays: list[LegalCommand], by_action: dict[str, list[LegalCommand]]) -> str:
        """Rule 13.43 with rally points: a broken unit goes to a leader out of sight.

        A broken squad rallies only with a leader in its hex (rule 14.3), and a broken unit
        that fails one more check is eliminated. So the rout goes first to a hex no enemy
        sees, then to the hex nearest an unbroken leader (the rally leader of its group
        first), then to the lowest loss, then away from the enemy. A stay is a choice only
        in a hex that no enemy sees; a unit in sight routs when it can.
        """
        leader_hexes: list[HexRef] = [
            u.hex
            for u in state.player_units(self.player)
            if u.kind == KIND_LEADER and not u.broken and u.hex is not None and u.carrier is None
        ]
        rally_hexes = {state.units[uid].hex for uid in self.rally_leaders.values() if state.units[uid].hex is not None}
        enemies = [u.hex for u in self._seen_enemies(state) if u.hex is not None and not u.broken]
        options: list[tuple[LegalCommand, HexRef]] = [(lc, lc.command.hex) for lc in routs if lc.command.hex is not None]
        for lc in stays:
            here = state.units[lc.command.units[0]].hex
            if here is None:
                continue
            if self._seen_by_enemy(state, here) and routs:
                continue
            options.append((lc, here))
        if not options:
            return self._first_of(by_action, ("rout", "stay", "end_phase"))
        best: LegalCommand | None = None
        best_key: tuple | None = None
        for lc, dst in options:
            unit = state.units[lc.command.units[0]]
            seen = 1 if self._seen_by_enemy(state, dst) else 0
            to_leader = min((geometry.distance(dst, h) for h in leader_hexes), default=99)
            rally = 0 if dst in rally_hexes else 1
            loss = self._loss(state, unit, dst, False)
            away = min((geometry.distance(dst, h) for h in enemies), default=99)
            key = (seen, to_leader, rally, loss, -away, 0 if lc.command.action == "stay" else 1, lc.id)
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
            if (
                self.v7.advance_take
                and dst not in self.assignment.get(unit.id, ())
                and not is_cover(self.engine.board, dst)
                and self._seen_by_enemy(state, dst)
            ):
                # The next enemy Prep Fire Phase fires at a unit that stands in the open in
                # its sight, and a KIA result takes the stack (rule 8.8). The advance goes
                # to cover, to dead ground, or into the target.
                continue
            enemies = [u for u in state.infantry_in(dst) if u.player != self.player and visible_to(state, u, self.player)]
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
            if self.v7.advance_take and favorable and dst in self.assignment.get(unit.id, ()) and unit.id not in self._rally_group:
                # The Advance Phase takes the building (rule 4.7): an empty hex of the
                # target, a hex of broken enemies, or an assault the odds favor.
                bonus += self.v7.take_bonus
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
            if u.player == self.opponent and u.broken and visible_to(state, u, self.player)
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

    # ---------------------------------------------------------- step 4, lookahead

    def _own_legal(self, state: State) -> DecisionFrame:
        """The legal list of the state the agent has (the player state), built one time."""
        if self._own_frame_key != state.seq or self._own_frame is None:
            self._own_frame = self.engine.legal_commands(state)
            self._own_frame_key = state.seq
        return self._own_frame

    def _position_value(self, state: State) -> int:
        """The worth of a position for this side, in the points of the step score.

        For each unbroken squad of ours on the board: its progress on the route to its
        target, its cover, the fire it gives, and less the expected loss where it stands
        (the track in the Movement Phase), with the stack it stands in, because a KIA
        result takes the stack (rule 8.8).
        """
        total = 0
        board = self.engine.board
        in_movement = state.phase == PHASE_MOVEMENT
        for unit in state.player_units(self.player):
            if unit.hex is None or unit.broken or unit.carrier is not None or not unit.is_infantry or unit.kind == KIND_LEADER:
                continue
            target = self.assignment.get(unit.id, self.open_objectives)
            urgency = self._urgency(state, unit.id, unit.hex)
            progress = -self._route_cost(state, target, unit.hex, True) if target else 0
            cover = self.v6.cover_preference if is_cover(board, unit.hex) else 0
            fire = self._fire_points(state, unit, unit.hex)
            chance = self._raw_exposure(state, unit, unit.hex, in_movement and unit.moved)
            stack = sum(1 for u in state.infantry_in(unit.hex) if u.player == self.player and not u.broken)
            penalty = chance * self.v7.loss_scale * max(1, stack) // odds.ONE
            total += progress * self.v6.aggression * urgency + cover + fire - penalty * self.v6.threat_aversion
        return total

    def _move(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        """The v6 move, and with `lookahead` a one ply look at the best K moves.

        The core applies each of the K moves to the player state (`slcore.player_state`),
        and the position value of the result decides between them. A move of the true
        list that the player state does not offer keeps its step score.
        """
        if self.v7.lookahead <= 0:
            return super()._move(state, by_action)
        cache: dict[HexRef, int] = {}
        scored: list[tuple[tuple[int, int, int], str, LegalCommand]] = []
        stand: dict[int, int] = {}
        for action in ("stack_move", "move"):
            for lc in by_action.get(action, []):
                unit = state.units[lc.command.units[0]]
                dst = lc.command.hex
                if unit.hex is None or dst is None or self._would_overstack(state, dst, lc.command.units):
                    continue
                pressed, value = self._step_score(state, unit.id, unit.hex, dst, cache, count=len(lc.command.units))
                if unit.id not in stand:
                    stand[unit.id] = self._stand_value(state, unit.id, cache)
                scored.append(((pressed, value - stand[unit.id], len(lc.command.units)), lc.id, lc))
        good = [item for item in scored if item[0][0] > 0 or item[0][1] > 0]
        if not good:
            return super()._move(state, by_action)
        good.sort(key=lambda item: (-item[0][0], -item[0][1], -item[0][2], item[1]))
        top = good[: self.v7.lookahead]
        if len(top) == 1:
            return top[0][2].id
        own = self._own_legal(state)
        best: LegalCommand | None = None
        best_key: tuple | None = None
        for rank, (score, cid, lc) in enumerate(top):
            if own.by_id(lc.id) is None:
                value = None
            else:
                after, _ = self.engine.apply(state, lc.command, own)
                value = self._position_value(after)
            # A forced step (pressed) stays ahead of one that is not, and the rank of the
            # step score breaks a tie and stands in for a move with no lookahead.
            key = (score[0], value if value is not None else -(10**9), -rank)
            if best_key is None or key > best_key:
                best, best_key = lc, key
        return best.id if best is not None else top[0][2].id

    def _prep_plans(self, state: State, by_action: dict[str, list[LegalCommand]], phase: str) -> list[Plan]:
        """The best plan at each target, best first, for the lookahead of the Prep Fire Phase."""
        plans: list[Plan] = []
        for target, adds in sorted(self._adds_by_target(by_action).items()):
            plan = self._plan_for(state, target, adds, phase)
            if plan is not None:
                plans.append(plan)
        plans.sort(key=lambda p: (-p.value, p.target))
        return plans

    def _prep_lookahead(self, state: State, by_action: dict[str, list[LegalCommand]], phase: str) -> str | None:
        """Step 4 in the Prep Fire Phase: the best K plans against the move each costs.

        A plan is worth its expected loss of the enemy in points, less the move advantage of
        each member it holds in its hex (rule 8.1). The plan with the best net worth fires
        when that worth is not below zero; else no plan fires and the force moves.
        """
        floor = SQUAD * self.v7.fire_floor // 100
        best: Plan | None = None
        best_net: int | None = None
        advantage: dict[int, int] = {}
        for plan in self._prep_plans(state, by_action, phase)[: self.v7.lookahead]:
            if plan.raw < floor:
                continue
            cost = 0
            for lc in plan.members:
                uid = lc.command.units[0]
                if uid not in advantage:
                    advantage[uid] = self._move_advantage(state, state.units[uid])
                cost += advantage[uid]
            net = plan.raw * self.v7.fire_weight // odds.ONE - cost
            if best_net is None or net > best_net:
                best, best_net = plan, net
        if best is None or best_net is None or best_net < 0:
            return None
        return best.members[0].id

    # ---------------------------------------------------------- step 5, the search

    MACROS: tuple[tuple[str, tuple[tuple[str, object], ...]], ...] = (
        ("plan", ()),
        ("press", (("aggression", 2), ("loss_scale", -2))),
        ("careful", (("loss_scale", 2), ("threat_aversion", 1))),
        ("mass", (("mass", True),)),
        ("hold", (("mass", True), ("schedule_margin", -99))),
    )
    # The prior of each macro. The plan of the odds is the policy the search improves on,
    # so it has the largest prior; each other macro shares the rest.
    PRIOR_PLAN = 40
    SEARCH_EXPLORE = 2  # the PUCT constant, in the units of the leaf value divided by SEARCH_SCALE
    SEARCH_SCALE = 16  # leaf value points for one unit of the PUCT constant
    BUILDING_POINTS = 32  # the leaf value of one building of the plan that this side controls

    def _macro_record(self, name: str) -> Parameters:
        base = self._base_v7
        for macro, changes in self.MACROS:
            if macro != name:
                continue
            values: dict[str, object] = {}
            for key, change in changes:
                current = getattr(base, key)
                if isinstance(change, bool) or key == "schedule_margin":
                    values[key] = change
                elif key == "loss_scale" and change == -2:
                    values[key] = max(1, current // 2)
                elif key == "loss_scale":
                    values[key] = current * int(change)
                else:
                    values[key] = current + int(change)
            return replace(base, **values)
        raise ValueError(f"no macro {name!r}")

    def _use_record(self, record: Parameters) -> None:
        """Play the rest of the player turn with this record. The caches that read it go."""
        self.v7 = record
        self.v6 = v6_parameters(record)
        self._fields = {}
        self._moves_along = {}
        self._group_key = ()

    def _search_window(self, state: State, frame: DecisionFrame) -> None:
        if self._base_v7.search_iterations <= 0 or not self.has_deadline:
            return
        if self._macro_turn is not None and (state.turn, state.phasing) != self._macro_turn:
            self._use_record(self._base_v7)
            self._macro_turn = None
        if (
            self._macro_turn is None
            and state.phasing == self.player
            and frame.phase == PHASE_MOVEMENT
            and frame.player == self.player
            and not state.game_over
        ):
            self._refresh_routes(state)
            self._refresh_objectives(state)
            name = self._search(state)
            self.macro_log.append((state.turn, name))
            self._use_record(self._macro_record(name))
            self._macro_turn = (state.turn, state.phasing)

    def _search(self, state: State) -> str:
        """PUCT over the macros of this player turn, with a rollout for each visit.

        Each rollout plays the rest of the player turn on the player state: this side with
        the record of the macro, the other side with the v7 record of its nation and role
        as the model of the enemy. The dice come from `search_seed`, the turn, and the
        rollout, so a search gives the same macro each time. The leaf value is the worth
        of the units of each side (`odds.unit_value`) and the buildings of the plan.
        """
        from slcore.rng import seed_state

        names = [name for name, _ in self.MACROS]
        rest = (100 - self.PRIOR_PLAN) // max(1, len(names) - 1)
        prior = {name: (self.PRIOR_PLAN if name == "plan" else rest) for name in names}
        visits = {name: 0 for name in names}
        totals = {name: 0 for name in names}
        root = self._leaf_value(state)
        for i in range(self._base_v7.search_iterations):
            n = sum(visits.values())

            def score(name: str) -> tuple[int, int, str]:
                q = (totals[name] * 100 // visits[name]) if visits[name] else 0
                # The exploration term, in the units of q (the leaf value times 100).
                u = self.SEARCH_EXPLORE * self.SEARCH_SCALE * prior[name] * _isqrt(max(1, n)) // (1 + visits[name])
                return (q + u, prior[name], name)

            name = max(names, key=score) if n else "plan"
            dice = seed_state((self._base_v7.search_seed * 1_000_003 + state.turn * 101 + self.player * 7 + i) & 0xFFFFFFFFFFFF)
            value = self._rollout(state.with_(rng=dice), self._macro_record(name)) - root
            visits[name] += 1
            totals[name] += value
        return max(names, key=lambda name: ((totals[name] * 100 // visits[name]) if visits[name] else -(10**12), visits[name], name))

    def _enemy_model(self, state: State) -> "ScriptedV7":
        from slcore.view import nationalities_of

        nation = nationalities_of(state).get(str(self.opponent), "")
        nation = "soviet" if nation == "russian" else nation
        try:
            record = profile_for(nation, side_defends(self.engine, self.opponent))
        except UnknownNation:
            record = Parameters()
        return ScriptedV7(self.engine, self.opponent, replace(record, search_iterations=0, lookahead=0))

    def _rollout(self, state: State, record: Parameters) -> int:
        """Play to the end of this player turn and give the leaf value."""
        agents = {self.player: ScriptedV7(self.engine, self.player, replace(record, search_iterations=0)), self.opponent: self._enemy_model(state)}
        turn = (state.turn, state.phasing)
        for _ in range(self._base_v7.search_commands):
            if state.game_over or (state.turn, state.phasing) != turn:
                break
            frame = self.engine.legal_commands(state)
            if not frame.commands:
                break
            chosen = frame.by_id(agents[frame.player].select(state, frame))
            if chosen is None:
                break
            state, _ = self.engine.apply(state, chosen.command, frame)
        return self._leaf_value(state)

    def _leaf_value(self, state: State) -> int:
        from slcore.rules import victory

        if state.game_over:
            side = self.engine.scenario.players()[self.player]
            if state.result == side:
                return 10_000
            if state.result and state.result != "draw":
                return -10_000
        types = self.engine.types
        value = 0
        for u in state.units:
            if u.eliminated or u.hex is None and u.carrier is None or u.kind == KIND_SW or u.is_vehicle:
                continue
            worth = odds.unit_value(types, u)
            value += worth if u.player == self.player else -worth
        board = self.engine.board
        for place_id, hexes in self._places():
            if len(hexes) > 1 or board.hex(hexes[0]).building is not None:
                if victory.controlled_by(state, board, place_id, self.player):
                    value += self.BUILDING_POINTS
        for place_id, _hexes in self.own_places:
            if victory.controlled_by(state, board, place_id, self.opponent):
                value -= self.BUILDING_POINTS
        return value


def _isqrt(n: int) -> int:
    """The integer square root, for the exploration term of the search."""
    import math

    return math.isqrt(n)
