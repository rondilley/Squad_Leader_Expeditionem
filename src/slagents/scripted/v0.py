"""Scripted agent v0: set up, move toward the objective, end phases.

Parameters: none in v0. It is deterministic for a state and a frame, so it
needs no generator. Ties break on command ID order, which is stable across
list sequences.
"""

from __future__ import annotations

from slcore import geometry
from slcore.engine import Engine
from slcore.frame import DecisionFrame, LegalCommand
from slcore.game import PHASE_ADVANCE, PHASE_MOVEMENT, PHASE_SETUP, State
from slcore.geometry import HexRef


class ScriptedV0:
    name = "scripted"
    version = "0"

    def __init__(self, engine: Engine, player: int) -> None:
        self.engine = engine
        self.player = player
        self.objectives: tuple[HexRef, ...] = engine.objectives(player)

    def _distance_to_objective(self, hex_ref: HexRef) -> int:
        if not self.objectives:
            return 0
        return min(geometry.distance(hex_ref, o) for o in self.objectives)

    def select(self, state: State, frame: DecisionFrame) -> str:
        if not frame.commands:
            raise ValueError("no legal command")
        by_action: dict[str, list[LegalCommand]] = {}
        for lc in frame.commands:
            by_action.setdefault(lc.command.action, []).append(lc)
        if frame.phase == PHASE_SETUP:
            for action in ("place_weapon", "place", "end_setup"):
                if action in by_action:
                    return min(by_action[action], key=lambda lc: lc.id).id
        if frame.phase in (PHASE_MOVEMENT, PHASE_ADVANCE):
            best: LegalCommand | None = None
            best_gain = 0
            for action in ("stack_move", "move", "advance"):
                for lc in by_action.get(action, []):
                    unit = state.units[lc.command.units[0]]
                    if unit.hex is None or lc.command.hex is None:
                        continue
                    gain = self._distance_to_objective(unit.hex) - self._distance_to_objective(lc.command.hex)
                    if gain > best_gain or (gain == best_gain and gain > 0 and best is not None and lc.id < best.id):
                        best = lc
                        best_gain = gain
            if best is not None:
                return best.id
        if "end_phase" in by_action:
            return by_action["end_phase"][0].id
        moves = by_action.get("stack_move", []) + by_action.get("move", [])
        if moves:
            # Rule 6.3: the phase cannot end while a hex is over a limit. Only a move
            # relieves it, because the portage of a hex counts a weapon on its ground.
            return min(moves, key=lambda lc: lc.id).id
        return min(frame.commands, key=lambda lc: lc.id).id
