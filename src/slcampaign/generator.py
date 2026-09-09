"""Random scenario construction (FR-17, Game Set IV).

The design-your-own rules build a scenario from a sequence of draws. The printed method
draws playing cards; this project draws from the seeded generator of the core, because a
game is its seed and its command log, and a scenario that a seed cannot rebuild is not
reproducible (NFR-04).

What each draw decides, in the order of the printed method:

1. The board. The printed method names one of the four boards; this project names one of
   the four board types of FR-25, and the board generator makes it.
2. The nationality of the defender: Axis or Allied first, then American or Russian.
3. The board area the defender sets up in.
4. The length of the game: four, six, eight, or ten turns.
5. The defending force, from a selection table.
6. The victory condition, from a victory table.

Two of the printed tables are pictures on the rules sheet, and the text of the rulebook
does not carry them, so the project cannot transcribe them. Open item O-08 asks the owner
to read the Point Value Chart and the Random Selection Chart off the sheet. Until then the
selection table here is the project's own, built from the point scale in `points.py`. The
victory table is the printed list, and it holds the entries that rules 1 to 27 can decide;
an entry that needs the armor game, the artillery rules, or the night rules is not in it.

Rule 10 of the printed method makes the attacker the player whose force costs less. Both
forces here come from one seed, so the module gives the attacker a share of the defender
point total and says what that share is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from slboards.generator import BOARD_TYPES
from slcore.rng import RngState, choice_index, seed_state
from slcore.units import KIND_LEADER, KIND_SW, UnitType

TURNS = (4, 6, 8, 10)
AXIS = "german"
ALLIED = ("russian", "american")

# Rule 6 of the printed method, in the entries that rules 1 to 27 can decide. Each entry
# is a victory condition of `slcore.rules.victory` with its parameters.
VICTORY_TABLE = (
    ("sole_occupant", "the attacker is the sole occupant of one building of the defender at the end"),
    ("building_count", "the attacker holds a majority of the buildings of the defender"),
    ("force_eliminated", "the defending force is eliminated"),
    ("casualty_exchange", "the attacker eliminates more squads than it loses"),
    ("unbroken_squad_ratio", "the attacker has more unbroken squads than the defender at the end"),
)

# The share of the defender point total that the attacker gets. Rule 10 of the printed
# method makes the cheaper force the attacker, and an attack on a held position needs the
# larger force, so the share is above one in each row. The row comes from a draw.
ATTACK_SHARE = ((3, 2), (5, 3), (7, 4), (2, 1))

MIN_SQUADS = 3
MAX_SQUADS = 12
MIN_POINTS = 120


class ScenarioError(Exception):
    """The construction cannot build a scenario from these parameters."""


@dataclass(frozen=True)
class Force:
    """One side of a random scenario: a count for each counter type key."""

    nationality: str
    counts: tuple[tuple[str, int], ...] = field(default_factory=tuple)

    def points(self, values: Mapping[str, int]) -> int:
        return sum(values[key] * n for key, n in self.counts)

    def squads(self, types: Mapping[str, UnitType]) -> int:
        return sum(n for key, n in self.counts if types[key].is_squad_like)

    def to_dict(self) -> dict[str, Any]:
        return {"nationality": self.nationality, "counts": {k: n for k, n in self.counts}}


@dataclass(frozen=True)
class Draw:
    """What the draws decided, so that a run artifact can show the construction."""

    board_type: str
    defender: str
    attacker: str
    turns: int
    victory_kind: str
    victory_text: str
    attack_share: tuple[int, int]
    defender_points: int
    attacker_points: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "board_type": self.board_type,
            "defender": self.defender,
            "attacker": self.attacker,
            "turns": self.turns,
            "victory": {"kind": self.victory_kind, "text": self.victory_text},
            "attack_share": list(self.attack_share),
            "defender_points": self.defender_points,
            "attacker_points": self.attacker_points,
        }


def army_types(types: Mapping[str, UnitType], nationality: str) -> dict[str, UnitType]:
    return {k: v for k, v in types.items() if k.split(":")[0] == nationality}


def pick(rng: RngState, items) -> tuple[RngState, Any]:
    rng, index = choice_index(rng, len(items))
    return rng, items[index]


def build_force(
    rng: RngState,
    types: Mapping[str, UnitType],
    values: Mapping[str, int],
    nationality: str,
    budget: int,
) -> tuple[RngState, Force]:
    """A force that costs at most `budget`, with a leader, some squads, and some weapons.

    The order matters. A force needs a leader first, because rule 14.1 rallies a broken
    squad only with a leader in the hex. Then it takes squads until the budget is low, and
    it spends what is left on support weapons that the squads can carry.
    """
    army = army_types(types, nationality)
    leaders = sorted(k for k, t in army.items() if t.kind == KIND_LEADER)
    squads = sorted(k for k, t in army.items() if t.is_squad_like)
    weapons = sorted(k for k, t in army.items() if t.kind == KIND_SW)
    if not leaders or not squads:
        raise ScenarioError(f"the army {nationality!r} has no leader or no squad in the counter data")

    counts: dict[str, int] = {}
    rng, leader = pick(rng, leaders)
    counts[leader] = 1
    spent = values[leader]

    taken = 0
    while taken < MAX_SQUADS:
        affordable = [k for k in squads if spent + values[k] <= budget]
        if not affordable or (taken >= MIN_SQUADS and spent * 4 >= budget * 3):
            break
        rng, key = pick(rng, affordable)
        counts[key] = counts.get(key, 0) + 1
        spent += values[key]
        taken += 1
    if taken < MIN_SQUADS:
        raise ScenarioError(
            f"a budget of {budget} points buys {taken} squads of {nationality}, and a force needs {MIN_SQUADS}"
        )

    # Rule 5.7 gives a squad three portage points, so the weapon count follows the squads.
    room = taken
    while weapons and room > 0:
        affordable = [k for k in weapons if spent + values[k] <= budget]
        if not affordable:
            break
        rng, key = pick(rng, affordable)
        counts[key] = counts.get(key, 0) + 1
        spent += values[key]
        room -= 1
    return rng, Force(nationality, tuple(sorted(counts.items())))


def draw_scenario(
    seed: int,
    types: Mapping[str, UnitType],
    values: Mapping[str, int],
    points: int = 400,
) -> tuple[Draw, Force, Force]:
    """The six draws of the printed method, and the two forces they give.

    `points` is the point total of the defending force. Rule 10 gives the attacker more,
    because it attacks a position that is already set up.
    """
    if points < MIN_POINTS:
        raise ScenarioError(f"a scenario needs at least {MIN_POINTS} points a side, and not {points}")
    rng = seed_state(seed)
    rng, board_type = pick(rng, BOARD_TYPES)
    rng, allied_first = choice_index(rng, 2)
    rng, allied_army = pick(rng, ALLIED)
    defender = allied_army if allied_first else AXIS
    attacker = AXIS if allied_first else allied_army
    rng, turns = pick(rng, TURNS)
    rng, victory = pick(rng, VICTORY_TABLE)
    rng, share = pick(rng, ATTACK_SHARE)
    attacker_points = points * share[0] // share[1]
    rng, defending = build_force(rng, types, values, defender, points)
    rng, attacking = build_force(rng, types, values, attacker, attacker_points)
    draw = Draw(
        board_type=board_type,
        defender=defender,
        attacker=attacker,
        turns=turns,
        victory_kind=victory[0],
        victory_text=victory[1],
        attack_share=share,
        defender_points=defending.points(values),
        attacker_points=attacking.points(values),
    )
    return draw, defending, attacking
