"""The victory conditions of a game as one viewer may read them (the frame field `objectives`).

A person must see during play what each side must do to win. The window has no rule logic
(AR-06), so the host gives one record for each victory condition of the scenario:

- `side`: the player index of the side the condition is for, and `side_name`.
- `kind`, and `note`: the sentence of the card for the condition, when the scenario has one.
- `hexes`: the hexes the condition names (the hexes of the building of a group), or none
  for a condition with no hexes (a ratio of squads, for example). The hexes are on the card,
  so each viewer gets them.
- `status`: the present count of the condition, only for the viewer's own side, with the
  hexes the side controls now (`held`). The core tests the condition on the state that the
  viewer may know (`player_state.for_player`), so the count gives no fact of a hidden unit of
  the other side (AR-09). A watcher of two computer sides gets each status.
- `turns`: the count of turns of the scenario. The core tests the conditions at the end of
  the last turn, and a sudden-death condition at the end of each phase.
"""

from __future__ import annotations

from typing import Any

from slcore import geometry
from slcore.engine import Engine
from slcore.game import State
from slcore.player_state import for_player
from slcore.rules import victory


def condition_hexes(engine: Engine, kind: str, params: dict[str, Any]) -> list:
    """The hexes that a condition names: the building hexes of its groups."""
    scenario, board = engine.scenario, engine.board
    if kind in (victory.KIND_HEX_CONTROL, victory.KIND_SOLE_OCCUPANT):
        return victory.group_hexes(scenario, board, params.get("groups", []))
    if kind == victory.KIND_BUILDING_COUNT:
        groups = params.get("groups", [])
    elif kind == victory.KIND_BUILDING_SWING:
        groups = list(params.get("enemy_groups", [])) + list(params.get("own_groups", []))
    else:
        return []
    buildings = victory.buildings_on(board)
    out: list = []
    for building in victory.group_buildings(scenario, board, groups):
        out.extend(buildings.get(building, ()))
    return sorted(set(out))


def document(engine: Engine, state: State, viewer: int, sides: dict[int, str], spectator: bool = False) -> list[dict[str, Any]]:
    """The records of the victory conditions for one viewer. `viewer` is the player index of
    the frame; a spectator reads each status."""
    scenario = engine.scenario
    known = state if spectator else for_player(state, viewer)
    out: list[dict[str, Any]] = []
    for condition in scenario.victory:
        params = dict(condition.params)
        side_key = str(params.get("side", ""))
        side = scenario.side_index(side_key) if side_key else 0
        hexes = condition_hexes(engine, condition.kind, params)
        record: dict[str, Any] = {
            "side": side,
            "side_name": sides.get(side, side_key),
            "kind": condition.kind,
            "note": str(params.get("note", "")),
            "hexes": [geometry.hex_id(*h) for h in hexes],
            "turns": scenario.turns,
        }
        if spectator or side == viewer:
            result = victory.evaluate_condition(known, engine.board, scenario, engine.types, condition)
            held = []
            if condition.kind == victory.KIND_HEX_CONTROL:
                held = [geometry.hex_id(*h) for h in hexes if victory.hex_controlled_by(known, h, side)]
            elif condition.kind == victory.KIND_SOLE_OCCUPANT:
                held = [
                    geometry.hex_id(*h)
                    for h in hexes
                    if any(u.player == side and not u.broken for u in known.infantry_in(h))
                ]
            record["status"] = {
                "count": result.count,
                "threshold": result.threshold,
                "satisfied": result.satisfied,
                "detail": result.detail,
                "held": held,
            }
        out.append(record)
    return out
