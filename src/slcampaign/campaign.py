"""The Campaign Game of Game Set IV (FR-17).

A campaign is a sequence of scenarios, and one leader counter carries a rank and a
performance total from one to the next. Rule 1 says how a player does in one scenario
influences the chances of advancement, and indirectly of survival, in the next.

The rules this module applies, from `sldata/tables/campaign.json`:

- Rule 3.1: seven ranks, each with the morale and the leadership of its counter. The
  personal leader joins the counter mix of the scenario (rule 3.2), so the rank decides
  what the player commands.
- Rule 4: Elan points and Cowardice points, awarded from the events of the game. Two Elan
  items need an armoured fighting vehicle, and the armor game waits for a subsequent tier,
  so the scorer does not award them and the table records why.
- Rule 2.4 and 2.6: a performance total of ten or more promotes one rank and takes ten off
  the total. A total of minus ten or less demotes one rank and adds ten. One rank each
  scenario, and the rest of the points carry over.
- Rule 2.7: a leader who is killed, or who is busted below Corporal, starts the next
  scenario as a new Corporal with a new name.
- Rule 5: one victory point for each scenario won, and one for each rank above Corporal
  that the leader holds at the end, when that leader survived the last scenario.

How the scorer reads a game. The core writes one event for each rule it applies, and each
event carries the units it acted on. So the scorer walks the events in order and holds a
small amount of state: which leader is directing the fire of this moment (rule 15.2), and
whether the last unit that broke was the personal leader (rule 12.22). That is what turns
a list of events into the personnel file of rule 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from sldata.loaders import read_data

CAMPAIGN_FILE = "tables/campaign.json"

# The events the scorer reads, by rule and kind.
FIRE_LEADER = ("15.2", "group_leader")
PHASE = ("4", "phase")
RALLIED = ("14.2", "rallied")
BROKEN = ("12.3", "broken")
MALFUNCTION = ("18.1", "malfunction")
CC_KILL = ("20.3", "cc_kill")
RALLY_DISASTER = ("18.3", "eliminated")
MORALE_ELIMINATED = ("13.6", "eliminated")
FIRE_ELIMINATED = ("8.8", "eliminated")
CC_ELIMINATED = (("20.71", "eliminated"), ("20.9", "eliminated"))
CAUSE_FIRE = "fire"
CAUSE_LEADER_BREAK = "leader_break"
BREAKS_FOR_COWARDICE = 2


class CampaignError(Exception):
    """The campaign cannot go on."""


@dataclass(frozen=True)
class Rank:
    name: str
    title: str
    morale: int
    leadership: int


@dataclass(frozen=True)
class Rules:
    """The campaign table, read one time."""

    ranks: tuple[Rank, ...]
    elan: dict[str, int]
    cowardice: dict[str, int]
    threshold: int
    scenarios: int

    def rank(self, index: int) -> Rank:
        return self.ranks[max(0, min(index, len(self.ranks) - 1))]

    def counter_for(self, index: int) -> str:
        """The counter type key of a rank: the morale and the leadership of rule 3.1."""
        r = self.rank(index)
        return f"{r.morale}-{abs(r.leadership)}"


def load_rules() -> Rules:
    document = read_data(CAMPAIGN_FILE)
    ranks = tuple(
        Rank(str(r["name"]), str(r["title"]), int(r["morale"]), int(r["leadership"]))
        for r in document["ranks"]
    )
    return Rules(
        ranks=ranks,
        elan={str(r["id"]): int(r["points"]) for r in document["elan"]},
        cowardice={str(r["id"]): int(r["points"]) for r in document["cowardice"]},
        threshold=int(document["promotion_threshold"]),
        scenarios=int(document["scenarios_in_a_campaign"]),
    )


@dataclass(frozen=True)
class Performance:
    """One personnel file line: rule 2.2 and rule 2.3."""

    elan: int = 0
    cowardice: int = 0
    awards: tuple[tuple[str, int], ...] = ()
    killed: bool = False

    @property
    def total(self) -> int:
        return self.elan + self.cowardice

    def to_dict(self) -> dict[str, Any]:
        return {
            "elan": self.elan,
            "cowardice": self.cowardice,
            "total": self.total,
            "killed": self.killed,
            "awards": [{"rule": rule, "points": points} for rule, points in self.awards],
        }


@dataclass(frozen=True)
class Leader:
    """The personal leader counter of rule 3."""

    name: str
    rank_index: int = 0
    carried: int = 0
    scenarios: int = 0
    replaced: bool = False

    def to_dict(self, rules: Rules) -> dict[str, Any]:
        rank = rules.rank(self.rank_index)
        return {
            "name": self.name,
            "rank": rank.name,
            "title": rank.title,
            "counter": rules.counter_for(self.rank_index),
            "carried_points": self.carried,
            "scenarios": self.scenarios,
            "replaced_the_one_before": self.replaced,
        }


def score(events: Sequence[Mapping[str, Any]], leader_id: int, player: int, won: bool, rules: Rules) -> Performance:
    """The Elan and the Cowardice points of one scenario, from the event log (rule 4)."""
    elan = 0
    cowardice = 0
    awards: list[tuple[str, int]] = []

    def award(rule_id: str, points: int) -> None:
        nonlocal elan, cowardice
        if points >= 0:
            elan += points
        else:
            cowardice += points
        awards.append((rule_id, points))

    directing = None
    leader_just_broke = False
    breaks = 0
    killed = False
    where: str | None = None

    for event in events:
        key = (str(event.get("rule_id")), str(event.get("kind")))
        data = event.get("data") or {}
        if data.get("unit") == leader_id and data.get("hex"):
            where = str(data["hex"])

        if key == FIRE_LEADER:
            directing = data.get("leader")
            leader_just_broke = False
            continue
        if key == PHASE:
            directing = None
            leader_just_broke = False
            continue

        if key == RALLIED and data.get("leader") == leader_id and data.get("unit") != leader_id:
            award("4.1D", rules.elan["4.1D"])
            continue

        if key == BROKEN:
            if data.get("unit") == leader_id:
                if str(data.get("cause")) == CAUSE_FIRE:
                    award("4.2E", rules.cowardice["4.2E"])
                breaks += 1
                leader_just_broke = True
                if breaks >= BREAKS_FOR_COWARDICE:
                    award("4.2A", rules.cowardice["4.2A"])
                    breaks = 0
            elif leader_just_broke and str(data.get("cause")) == CAUSE_LEADER_BREAK:
                award("4.2C", rules.cowardice["4.2C"])
            continue

        if key == MALFUNCTION and directing == leader_id:
            award("4.2D", rules.cowardice["4.2D"])
            continue

        if key == CC_KILL and (data.get("leader") == leader_id or leader_id in (data.get("attackers") or [])):
            award("4.1B", rules.elan["4.1B"])
            continue

        if key == RALLY_DISASTER:
            if data.get("unit") == leader_id:
                award("4.2A", rules.cowardice["4.2A"])
                killed = True
            elif where is not None and str(data.get("hex")) == where:
                award("4.2B", rules.cowardice["4.2B"])
            continue

        if key in (MORALE_ELIMINATED, FIRE_ELIMINATED) or key in CC_ELIMINATED:
            if data.get("unit") == leader_id:
                killed = True
            elif directing == leader_id and data.get("player") != player:
                award("4.1E", rules.elan["4.1E"])
            continue

    if won:
        award("4.1F", rules.elan["4.1F"])
    return Performance(elan=elan, cowardice=cowardice, awards=tuple(awards), killed=killed)


def advance(leader: Leader, performance: Performance, rules: Rules, next_name: str) -> tuple[Leader, bool]:
    """Rules 2.4 to 2.7: the rank and the points the leader carries to the next scenario.

    The second value says whether a new identity started, which rule 2.7 calls for after a
    leader is killed or busted below Corporal.
    """
    if performance.killed:
        return Leader(name=next_name, scenarios=leader.scenarios + 1, replaced=True), True
    total = leader.carried + performance.total
    rank_index = leader.rank_index
    if total >= rules.threshold:
        total -= rules.threshold
        rank_index = min(rank_index + 1, len(rules.ranks) - 1)
    elif total <= -rules.threshold:
        total += rules.threshold
        if rank_index == 0:
            # Rule 2.7: busted below Corporal, so a new identity starts at Corporal.
            return Leader(name=next_name, scenarios=leader.scenarios + 1, replaced=True), True
        rank_index -= 1
    return (
        replace(leader, rank_index=rank_index, carried=total, scenarios=leader.scenarios + 1, replaced=False),
        False,
    )


@dataclass
class Record:
    """One line of the campaign: the scenario, the result, and the personnel file."""

    index: int
    scenario_id: str
    seed: int
    won: bool
    result: str
    starting_rank: str
    ending_rank: str
    performance: Performance
    leader_name: str
    defence_points: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "scenario": self.scenario_id,
            "seed": self.seed,
            "defence_points": self.defence_points,
            "result": self.result,
            "won": self.won,
            "leader": self.leader_name,
            "starting_rank": self.starting_rank,
            "ending_rank": self.ending_rank,
            "performance": self.performance.to_dict(),
        }


@dataclass
class Campaign:
    """A campaign in progress: the leader, the record of each scenario, and the score."""

    rules: Rules
    leader: Leader
    records: list[Record] = field(default_factory=list)

    @property
    def scenarios_won(self) -> int:
        return sum(1 for r in self.records if r.won)

    def victory_points(self) -> int:
        """Rule 5.1: one point for each scenario won, one for each rank above Corporal.

        The leader that scores the rank points is the one that survived the last scenario.
        A leader that a KIA result removed is not on the file any more: rule 2.7 puts a new
        Corporal there, and a Corporal is worth no rank point.
        """
        points = self.scenarios_won
        if self.records and not self.leader.replaced:
            points += self.leader.rank_index
        return points

    def add(
        self,
        index: int,
        scenario_id: str,
        seed: int,
        result: str,
        won: bool,
        performance: Performance,
        next_name: str,
    ) -> bool:
        """One line of the personnel file. Gives back whether a new identity started."""
        starting = self.rules.rank(self.leader.rank_index).name
        played = self.leader.name
        self.leader, fresh = advance(self.leader, performance, self.rules, next_name)
        self.records.append(
            Record(
                index=index,
                scenario_id=scenario_id,
                seed=seed,
                won=won,
                result=result,
                starting_rank=starting,
                ending_rank=self.rules.rank(self.leader.rank_index).name,
                performance=performance,
                leader_name=played,
            )
        )
        return fresh

    @property
    def scenarios_lost(self) -> int:
        return sum(1 for r in self.records if not r.won)

    def to_dict(self) -> dict[str, Any]:
        return {
            "leader": self.leader.to_dict(self.rules),
            "scenarios_played": len(self.records),
            "scenarios_won": self.scenarios_won,
            "victory_points": self.victory_points(),
            "tie_break_points": self.leader.carried,
            "records": [r.to_dict() for r in self.records],
        }


def names(seed: int, count: int) -> list[str]:
    """A name for each identity the campaign needs. Rule 2.7 can call for a new one."""
    return [f"Leader {seed}-{i + 1}" for i in range(count)]
