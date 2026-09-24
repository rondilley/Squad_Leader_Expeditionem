"""The shaped reward of the learned tier (FR-51, the strong-AI follow-up item e).

The first rung of the ladder (2026-09-12, `docs/reports/2026-09-12_training_run_1m.md`)
ran with a terminal reward only: plus one for a win, minus one for a loss, zero for a game
that hit the command limit. On the attacker side of scenario 1 a random policy does not
win, so the best return the learner found was the zero of a game that never ends, and it
held the game there with a pickup and a drop. The policy learned what the reward said.

The owner's instruction after that run is the design here. A game that is not won is a
defeat, so a loss and a truncation both cost `LOSS`, a large number. And the reward is not
at the end only. It pays for the things that raise the probability of a win, as the doctrine
research names them (RV-9, table A): find the enemy, shoot at it, hurt it, kill it, kill
its leaders, trap its routers, get to cover, stay out of its sight, hide, survive, hold the
objective, and win. The same terms with the sign turned are the costs: to be found, to be
shot at, to break, to lose men and weapons, to stand in the open in the enemy's sight.
Each term reads an event the core emitted, a count the core's own victory evaluator gives,
or the core's line of sight table, so no rule is restated here (AR-01).

Each side reads the same events and weighs them by its own doctrine (RV-9, table B). The
counts are zero-sum, what one side gains the other loses, and the weights are not: the
Soviet side pays less for a lost squad than the American side does, because the research
gives the Soviet side a high casualty tolerance and the American side a low one. So the
two rewards of one event differ, which is what a national doctrine is.

Each step also costs `step_cost` to the side that acted. A loop of commands that changes
nothing then bleeds, and a game of a thousand decisions costs a few points against a win
of a hundred.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from typing import Any, Mapping

from slcore import geometry
from slcore.engine import Engine
from slcore.events import Event
from slcore.game import State
from slcore.los_eval import evaluate as evaluate_los
from slcore.rules import victory
from slcore.rules.r13_rout import is_cover
from slcore.units import KIND_LEADER, KIND_SW

WIN = 100.0
LOSS = -100.0

# The victory conditions that name a place. Progress on one of them is the objective term.
POSITIONAL_KINDS = (
    victory.KIND_BUILDING_SWING,
    victory.KIND_BUILDING_COUNT,
    victory.KIND_HEX_CONTROL,
    victory.KIND_SOLE_OCCUPANT,
)

# The terms that are a loss of men or material when their count is negative. A side's
# casualty tolerance scales the cost of these and nothing else (RV-9, table B).
LOSS_TERMS = ("hurt", "kill", "kill_leader", "kill_weapon", "kill_vehicle", "malfunction")


@dataclass(frozen=True)
class RewardWeights:
    """The named weights of the shaped reward. A run artifact records them.

    Each weight is the value of one count of its term. The count is positive for the side
    that gained and negative for the side that lost, so one weight serves both signs. The
    comment on each term names the principle of RV-9 table A it pays for.
    """

    find: float = 0.5  # P20: an enemy stack loses its concealment (rule 25)
    fire: float = 0.1  # P1, P3: one fire result against an enemy hex (rule 10.5)
    hurt: float = 1.0  # P2, P12: an enemy unit breaks (rule 12.3)
    kill: float = 2.0  # an enemy squad or crew is removed
    kill_leader: float = 3.0  # P12: an enemy leader is removed
    kill_weapon: float = 0.5  # an enemy support weapon is removed, or fails its repair (rule 18.2)
    kill_vehicle: float = 4.0  # an enemy vehicle becomes a wreck (rule 40.1)
    trap: float = 1.0  # P11: a broken enemy dies with no rout route (rule 13.47), added to the kill
    malfunction: float = 0.25  # an enemy weapon or gun malfunctions (rule 18.1)
    cover: float = 0.2  # P7: an own unit ends a move or an advance in cover
    sneak: float = 0.2  # P9: an own unit ends a move or an advance where no unbroken enemy sees it
    exposed: float = 0.3  # P8: an own unit ends a move or an advance in the open, in an enemy's sight
    hide: float = 0.5  # P10, P16: an own stack gains a concealment counter (rule 25.3)
    survive: float = 0.25  # an own unit passes a morale check, or rallies (rules 12.1, 14.2)
    objective: float = 5.0  # P17: one unit of progress on a positional victory condition, each player turn
    step_cost: float = 0.01  # each command, charged to the side that gave it
    casualty_tolerance: float = 1.0  # table B: divides the cost of an own loss; above one is tolerant
    win: float = WIN
    loss: float = LOSS  # a loss, a draw, and a truncation each cost this
    nation: str = "universal"

    def value(self, counts: Mapping[str, float]) -> float:
        total = 0.0
        for term, count in counts.items():
            weight = getattr(self, term, None)
            if weight is None:
                continue
            if count < 0 and term in LOSS_TERMS and self.casualty_tolerance > 0:
                count = count / self.casualty_tolerance
            total += weight * count
        return total

    def to_dict(self) -> dict[str, Any]:
        return {
            "nation": self.nation,
            "find": self.find,
            "fire": self.fire,
            "hurt": self.hurt,
            "kill": self.kill,
            "kill_leader": self.kill_leader,
            "kill_weapon": self.kill_weapon,
            "kill_vehicle": self.kill_vehicle,
            "trap": self.trap,
            "malfunction": self.malfunction,
            "cover": self.cover,
            "sneak": self.sneak,
            "exposed": self.exposed,
            "hide": self.hide,
            "survive": self.survive,
            "objective": self.objective,
            "step_cost": self.step_cost,
            "casualty_tolerance": self.casualty_tolerance,
            "win": self.win,
            "loss": self.loss,
        }


def with_weights(**changes: Any) -> RewardWeights:
    return replace(RewardWeights(), **changes)


# The national biases of RV-9 table B as weight changes. Each line names its cell.
#
# German: aggression high and counterattack high (Citino), so the objective term is up and
# the exposure cost is down. Command flexibility high has no reward term, because it is
# a property of the policy and not of the outcome. Casualty tolerance medium.
#
# Soviet: casualty tolerance high (weak), so an own loss costs less. Reconnaissance low
# (weak), so a find is worth less. Close combat medium. The anti-tank items of the Soviet
# profile (Pakfront, PTOP) are the well-sourced half, and they show as a higher value on
# a vehicle kill. The cells marked weak in the table are weak here too.
#
# American: support fire high (FM 7-10), so fire and hurt are up. Casualty tolerance low
# to medium, so an own loss costs more, and cover and exposure weigh more. Aggression
# medium, so the objective term stays.
#
# British: unsourced. The universal weights, with no bias, until the research pass lands.
NATION_WEIGHTS: dict[str, RewardWeights] = {
    "german": with_weights(nation="german", objective=6.0, exposed=0.25, hurt=1.1, casualty_tolerance=1.0),
    "soviet": with_weights(nation="soviet", casualty_tolerance=1.4, find=0.35, exposed=0.2, kill_vehicle=5.0, objective=5.5),
    "american": with_weights(nation="american", fire=0.15, hurt=1.2, casualty_tolerance=0.8, cover=0.3, exposed=0.4),
}

# The armies of the counter set map onto the profiles. Russian counters play the Soviet
# doctrine. An army with no profile plays the universal weights.
NATION_OF_ARMY = {"german": "german", "russian": "soviet", "soviet": "soviet", "american": "american", "us": "american"}


def doctrine_weights(army: str | None) -> RewardWeights:
    """The reward weights of an army, from RV-9 table B, or the universal weights."""
    if not army:
        return RewardWeights()
    nation = NATION_OF_ARMY.get(army.strip().lower())
    if nation is None:
        return RewardWeights()
    return NATION_WEIGHTS[nation]


def weights_for_scenario(engine: Engine) -> tuple[RewardWeights, RewardWeights]:
    """The weights of the two players, from the army each side fields."""
    out = []
    for side in engine.scenario.players():
        out.append(doctrine_weights(engine.scenario.side_spec(side).nationality))
    return out[0], out[1]


def objective_progress(engine: Engine, state: State) -> tuple[int, int]:
    """The count of each side on its positional victory conditions, from the core's evaluator.

    A building swing gives the buildings taken minus the buildings lost. A hex count gives
    the hexes held. A side with no positional condition has zero, so the defender of
    scenario 1 gets its objective reward from what the attacker fails to take.
    """
    _, _, results = victory.evaluate(state, engine.board, engine.scenario, engine.types)
    sides = engine.scenario.players()
    progress = [0, 0]
    for r in results:
        if r.kind in POSITIONAL_KINDS and r.side in sides:
            progress[sides.index(r.side)] += r.count
    return progress[0], progress[1]


def objective_swing(delta_0: int, delta_1: int) -> int:
    """The objective payment for player 0. Player 1 receives the opposite.

    A condition that only one side has pays its whole change. Scenario 3A gives both
    sides a hex count of the same factory. A hex that changes hands would otherwise
    pay once for the gain and once for the loss. The shared part pays one time.
    A private change, such as a building swing, still pays.
    """
    if delta_0 == 0 or delta_1 == 0 or (delta_0 > 0) == (delta_1 > 0):
        return delta_0 - delta_1
    shared = min(abs(delta_0), abs(delta_1))
    extra_0 = abs(delta_0) - shared
    extra_1 = abs(delta_1) - shared
    swing = (1 if delta_0 > 0 else -1) * (shared + extra_0)
    swing -= (1 if delta_1 > 0 else -1) * extra_1
    return swing


def _unit_of(before: State, data: Mapping[str, Any], key: str = "unit"):
    uid = data.get(key)
    if uid is None:
        return None
    uid = int(uid)
    if not 0 <= uid < len(before.units):
        return None
    return before.units[uid]


def _seen_by_enemy(engine: Engine, state: State, player: int, hex_ref) -> bool:
    """Whether an unbroken enemy unit has a clear line of sight to the hex."""
    from slcore.view import visible_to

    for enemy in state.player_units(1 - player):
        if enemy.hex is None or enemy.broken or enemy.eliminated:
            continue
        if not visible_to(state, enemy, player):
            continue
        if evaluate_los(engine.board, engine.los, enemy.hex, hex_ref).clear:
            return True
    return False


def term_counts(engine: Engine, before: State, after: State, events: list[Event]) -> tuple[Counter, Counter]:
    """The signed count of each term for the two players, from the events of one command.

    A count is zero-sum: the side that gained has plus one and the other side minus one.
    """
    counts: tuple[Counter, Counter] = (Counter(), Counter())

    def credit(player: int, term: str, amount: float = 1.0) -> None:
        counts[player][term] += amount
        counts[1 - player][term] -= amount

    for e in events:
        data = e.data
        kind = e.kind
        if kind == "unconcealed":
            owner = int(data.get("player", -1))
            if owner in (0, 1):
                credit(1 - owner, "find")
        elif kind == "concealed":
            owner = int(data.get("player", -1))
            if owner in (0, 1):
                credit(owner, "hide")
        elif kind == "fire_result":
            targets = [u for u in (_unit_of(before, {"unit": i}) for i in data.get("units", [])) if u is not None]
            firer = data.get("firer")
            if firer in (0, 1):
                credit(int(firer), "fire")
            elif targets and len({u.player for u in targets}) == 1:
                credit(1 - targets[0].player, "fire")
        elif kind == "broken":
            unit = _unit_of(before, data)
            if unit is not None:
                credit(1 - unit.player, "hurt")
        elif kind in ("eliminated", "crushed", "passenger_eliminated"):
            unit = _unit_of(before, data)
            if unit is not None:
                if unit.kind == KIND_SW:
                    credit(1 - unit.player, "kill_weapon")
                elif unit.kind == KIND_LEADER:
                    credit(1 - unit.player, "kill_leader")
                else:
                    credit(1 - unit.player, "kill")
                if data.get("cause") == "no rout route":
                    credit(1 - unit.player, "trap")
        elif kind == "cc_kill":
            for target in data.get("targets", []):
                unit = _unit_of(before, {"unit": target})
                if unit is not None and not unit.eliminated:
                    credit(1 - unit.player, "kill_leader" if unit.kind == KIND_LEADER else "kill")
        elif kind in ("morale_pass", "rallied"):
            unit = _unit_of(before, data)
            if unit is not None:
                credit(unit.player, "survive")
        elif kind in ("weapon_eliminated", "weapon_removed"):
            weapon = _unit_of(before, data, "weapon")
            if weapon is not None:
                credit(1 - weapon.player, "kill_weapon")
        elif kind in ("malfunction", "mg_malfunction", "gun_malfunction"):
            owner = _unit_of(before, data, "weapon") if "weapon" in data else _unit_of(before, data)
            if owner is not None:
                credit(1 - owner.player, "malfunction")
        elif kind == "wreck":
            unit = _unit_of(before, data)
            if unit is not None:
                credit(1 - unit.player, "kill_vehicle")
        elif kind in ("move", "stack_move", "advance"):
            unit = _unit_of(before, data, "leader" if kind == "stack_move" else "unit")
            if unit is None or "to" not in data:
                continue
            dst = geometry.parse_hex_id(str(data["to"]))
            count = len(data.get("units", [])) if kind == "stack_move" else 1
            seen = _seen_by_enemy(engine, after, unit.player, dst)
            if is_cover(engine.board, dst):
                credit(unit.player, "cover", count)
            elif seen:
                credit(unit.player, "exposed", -count)
            if not seen:
                credit(unit.player, "sneak", count)
    return counts


def event_rewards(engine: Engine, before: State, after: State, events: list[Event], weights: RewardWeights | tuple[RewardWeights, RewardWeights]) -> tuple[float, float]:
    """The reward of each player from the events of one command, by each player's weights."""
    pair = weights if isinstance(weights, tuple) else (weights, weights)
    counts = term_counts(engine, before, after, events)
    return pair[0].value(counts[0]), pair[1].value(counts[1])


def step_rewards(
    engine: Engine,
    before: State,
    after: State,
    events: list[Event],
    acted: int,
    weights: RewardWeights | tuple[RewardWeights, RewardWeights],
    progress_before: tuple[int, int],
) -> tuple[tuple[float, float], tuple[int, int]]:
    """The shaped reward of one command for the two players, and the objective progress after it.

    The objective term is paid at the end of each player turn, when the core records the
    building control (PR-07), so a unit that walks through a building and out again earns
    nothing. The step cost goes to the side that gave the command.
    """
    pair = weights if isinstance(weights, tuple) else (weights, weights)
    counts = term_counts(engine, before, after, events)
    counts[acted]["step_cost"] -= 1.0
    progress = progress_before
    if any(e.kind == "setup_done" for e in events):
        # The baseline. Before the set up a side controls none of its own buildings, so
        # the swing reads minus five; the set up is not progress, and it pays nothing.
        progress = objective_progress(engine, after)
    elif any(e.kind == "player_turn_end" for e in events):
        progress = objective_progress(engine, after)
        swing = objective_swing(progress[0] - progress_before[0], progress[1] - progress_before[1])
        counts[0]["objective"] += swing
        counts[1]["objective"] -= swing
    return (pair[0].value(counts[0]), pair[1].value(counts[1])), progress


def result_rewards(engine: Engine, result: str, truncated: bool, weights: RewardWeights | tuple[RewardWeights, RewardWeights]) -> tuple[float, float]:
    """The terminal reward: the win pays, and each other end is a defeat.

    A loss, a draw by the card, and a game that reached the command limit each cost the
    loss value, because a game that is not won is not a result the owner wants the policy
    to find comfortable.
    """
    pair = weights if isinstance(weights, tuple) else (weights, weights)
    sides = engine.scenario.players()
    if truncated or result not in sides:
        return pair[0].loss, pair[1].loss
    winner = sides.index(result)
    out = [pair[0].loss, pair[1].loss]
    out[winner] = pair[winner].win
    return out[0], out[1]
