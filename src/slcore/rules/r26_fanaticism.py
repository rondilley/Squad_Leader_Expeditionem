"""Rule 26, fanaticism.

A group of units is fanatic because of where it is, and not because of what it is. The
benefit is one dice roll modifier of minus one on each Morale Check and each Rally
Attempt, which is the same as one more point of morale (rule 26.1).

The scenario says which side and which place. Scenario 2 gives the benefit to the
Russian units in the Tractor Works, and a unit gains it and loses it when it enters and
leaves that building (rule 26.2). The state holds the side and the hexes, because the
core reads no scenario file.
"""

from __future__ import annotations

from slcore.game import State
from slcore.units import Unit

RULE_26_1 = "26.1"
RULE_26_2 = "26.2"

MODIFIER = -1


def modifier_for(state: State, unit: Unit) -> int:
    """Rule 26.1: minus one for a Morale Check or a Rally Attempt of a fanatic unit."""
    return MODIFIER if state.fanatic(unit) else 0
