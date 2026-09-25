"""The state as one player may know it (AR-09, S3 and S4 of the 2026-09-23 review).

An agent decides from this record and not from the authoritative state. The record has
the same shape as `State`, so each agent, each odds function, and the core `apply` read
it with no change. What the player may not know is not in it:

- An enemy unit that `view.visible_to` rejects (below a concealment counter of its side,
  or hidden by rule 42.1) is off the board in this record: no hex, no carrier, no track,
  and no status (broken, moved, fired). Its type and name are on the scenario card.
  The unit stays in the unit list, because a unit id is its index in that list. It is
  not eliminated, so a count of the losses of the other side does not change.
- An enemy unit that died below a concealment counter or while hidden keeps its
  elimination, but it has no hex, because its hex was a secret when it died.
- The concealment counters stay. A counter is public (rule 25.2), and a counter with no
  unit below it in this record is what the player knows of it: a dummy or a real stack.
- The generator state and the seed are a fixed value. With the true generator a player
  could calculate each future die. With the seed and the log a player could calculate
  each hidden placement.
- The open fire group and the close combat declarations name no masked unit. An enemy
  demolition charge and an enemy stack lost in the sewer are not in the record, because
  the view of the player does not show them either.

This module has no file access, no clock, and no print. It is a pure function of the
state and the player.
"""

from __future__ import annotations

from slcore.game import STATE_FIELDS, CcDeclaration, FireGroup, State
from slcore.rng import RngState
from slcore.units import Unit, copy_with
from slcore.view import concealed_from, hidden_from, visible_to

# The generator state and the seed of each player state. It is not a secret and it is not
# the true value, so a die that an agent calculates from it tells the agent nothing.
MASKED_RNG: RngState = (1, 2, 3, 4)
MASKED_SEED = 0


def masked(state: State, unit: Unit, player: int) -> bool:
    """True when this unit is not in the player's picture of the board."""
    if unit.player == player:
        return False
    if unit.eliminated:
        return hidden_from(state, unit, player) or concealed_from(state, unit, player)
    return not visible_to(state, unit, player)


def _off_board(unit: Unit) -> Unit:
    """The unit as a counter of the order of battle, with no place and no status.

    The scenario card prints the order of battle, so the identity, the type, and the
    name are public. Where the unit is, and whether it is broken, moved, or fired, is not.

    The answer reads the unit only, and a unit record never changes, so it is kept on the
    unit (`OFF_BOARD_ATTRIBUTE`, NFR-01). A copy made with `with_` does not keep it.
    """
    found = unit.__dict__.get(OFF_BOARD_ATTRIBUTE)
    if found is None:
        found = Unit(
            id=unit.id,
            player=unit.player,
            type_key=unit.type_key,
            kind=unit.kind,
            group=unit.group,
            name=unit.name,
            portage_max=unit.portage_max,
            eliminated=unit.eliminated,
        )
        unit.__dict__[OFF_BOARD_ATTRIBUTE] = found
    return found


# The name of the memo of `_off_board` on a unit. It is not a field of the record.
OFF_BOARD_ATTRIBUTE = "_off_board_memo"


def _fire_group(group: FireGroup | None, gone: set[int]) -> FireGroup | None:
    if group is None:
        return None
    members = tuple(m for m in group.members if m[0] not in gone and (m[1] is None or m[1] not in gone))
    leader = None if group.leader in gone else group.leader
    return FireGroup(group.target, members, leader)


def _declarations(declarations: tuple[CcDeclaration, ...], gone: set[int]) -> tuple[CcDeclaration, ...]:
    out: list[CcDeclaration] = []
    for d in declarations:
        attackers = tuple(u for u in d.attackers if u not in gone)
        if not attackers:
            continue
        targets = tuple(u for u in d.targets if u not in gone)
        leader = None if d.leader in gone else d.leader
        out.append(CcDeclaration(d.player, attackers, targets, leader))
    return tuple(out)


def for_player(state: State, player: int) -> State:
    """The state as this player may know it. The player's own units are the true units."""
    gone = {u.id for u in state.units if u.player != player and masked(state, u, player)}
    if gone:
        units = tuple(_off_board(u) if u.id in gone else u for u in state.units)
        fire_group = _fire_group(state.fire_group, gone)
    else:
        # Each unit is in the picture of the player: the list and the fire group are the
        # true ones, and they are not built again for each decision (NFR-01).
        units = state.units
        fire_group = state.fire_group
    # `copy_with` gives the `replace` copy with no memo of the true state in it: the
    # hash, the unit index, and the searches of the true state are not of this record.
    return copy_with(
        state,
        STATE_FIELDS,
        {
            "units": units,
            "rng": MASKED_RNG,
            "seed": MASKED_SEED,
            "fire_group": fire_group,
            "cc_declarations": _declarations(state.cc_declarations, gone),
            "demo": tuple(d for d in state.demo if d.player == player),
            "sewer_lost": tuple(p for p in state.sewer_lost if all(state.units[u].player == player for u in p.units)),
        },
    )


def leaks(state: State, player_state: State, player: int) -> list[str]:
    """What of the true state this player state would disclose. Empty when it is safe.

    The secrecy tests and the agent boundary tests call it. A unit that the true state
    masks must have no place and no status in the player state, and the generator must not
    be the true one.
    """
    found: list[str] = []
    if player_state.rng != MASKED_RNG:
        found.append("the generator state is not masked")
    if player_state.seed != MASKED_SEED:
        found.append("the seed is not masked")
    for u in state.units:
        if not masked(state, u, player):
            continue
        seen = player_state.units[u.id]
        if seen != _off_board(u):
            found.append(f"unit {u.id} of player {u.player} is masked and shows its place or status")
    for d in player_state.demo:
        if d.player != player:
            found.append(f"demolition charge {d.id} of the other side")
    return found
