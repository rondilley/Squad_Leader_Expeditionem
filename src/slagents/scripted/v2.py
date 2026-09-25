"""Scripted agent v2: the engineer. It uses the rules that v1 does not.

Agent v1 plays rules 1 to 21. It sees a smoke command, a demolition charge, a
flamethrower, and a sewer entrance as commands it has no policy for, so it ends the
window instead. Agent v2 has a policy for each of them.

The named parameters (FR-44) say how far it will carry each of those tools:

- `aggression`, `cover_preference`, and `fire_priority` are the three that FR-44 names.
  They keep the meaning that v1 gives them.
- `smoke_range`: the distance at which an enemy is close enough to be worth a smoke
  counter (rule 24.3).
- `charge_range`: the distance at which the agent puts a demolition charge on a hex
  (rule 23.3). A charge on an occupied hex is always worth it.
- `use_sewers`: whether the agent takes a stack down a sewer entrance (rule 27.2).
- `dummy_share`: how many of the concealment counters go on empty hexes as dummies
  (rule 25.7), in tenths.

The agent is deterministic for a state and a frame, so a game of v2 against v2 replays.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from slcore import geometry
from slcore.engine import Engine
from slcore.frame import DecisionFrame, LegalCommand
from slcore.game import PHASE_SETUP, State
from slcore.geometry import HexRef
from slcore.rules import r10_resolution
from slcore.view import visible_to
from slagents.scripted.v1 import Parameters as V1Parameters
from slagents.scripted.v1 import ScriptedV1


@dataclass(frozen=True)
class Parameters(V1Parameters):
    """The named parameters of the engineer agent."""

    smoke_range: int = 6
    charge_range: int = 1
    use_sewers: bool = True
    dummy_share: int = 5


class ScriptedV2(ScriptedV1):
    name = "engineer"
    version = "2"

    def __init__(self, engine: Engine, player: int, params: Parameters | None = None) -> None:
        super().__init__(engine, player, params or Parameters())
        self.params: Parameters = params or Parameters()

    # ------------------------------------------------------------- selection

    def select(self, state: State, frame: DecisionFrame) -> str:
        if not frame.commands:
            raise ValueError("no legal command")
        by_action: dict[str, list[LegalCommand]] = {}
        for lc in frame.commands:
            by_action.setdefault(lc.command.action, []).append(lc)
        if frame.sub_step == "smoke_window":
            return self._smoke(state, by_action)
        if frame.sub_step == "demo_window":
            return self._explode(by_action)
        if frame.sub_step == "sewer_return":
            return self._sewer_return(state, by_action)
        if frame.phase == PHASE_SETUP and self._counters_first(by_action):
            return self._conceal(state, by_action)
        if "ft_fire" in by_action:
            return self._flamethrower(state, by_action)
        if "place_demo" in by_action:
            charge = self._charge(state, by_action)
            if charge is not None:
                return charge
        if "sewer_move" in by_action and self.params.use_sewers:
            sewer = self._sewer(state, by_action)
            if sewer is not None:
                return sewer
        return super().select(state, frame)

    def _counters_first(self, by_action: dict[str, list[LegalCommand]]) -> bool:
        """The counters go down after the units, because a counter hides a stack (rule 25.2)."""
        if "place_concealment" not in by_action:
            return False
        return not by_action.get("place_weapon") and not by_action.get("place")

    # ---------------------------------------------------------------- rule 24

    def _smoke(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        """Rule 24.3: smoke between the enemy and the hex the agent wants to cross."""
        best: LegalCommand | None = None
        best_score: int | None = None
        for lc in by_action.get("place_smoke", []):
            target = lc.command.hex
            if target is None:
                continue
            distance = self._enemy_distance(state, target)
            if distance > self.params.smoke_range:
                continue
            score = self.params.smoke_range - distance
            if best_score is None or score > best_score or (score == best_score and best is not None and lc.id < best.id):
                best = lc
                best_score = score
        if best is not None:
            return best.id
        return self._first_of(by_action, ("end_phase",))

    # ---------------------------------------------------------------- rule 23

    def _charge(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str | None:
        """Rule 23.3: a charge goes on the hex with the most enemy units near the unit."""
        best: LegalCommand | None = None
        best_score: tuple[int, int] | None = None
        for lc in by_action.get("place_demo", []):
            target = lc.command.hex
            if target is None:
                continue
            enemies = sum(1 for u in state.infantry_in(target) if u.player != self.player and visible_to(state, u, self.player))
            if enemies == 0 and self._enemy_distance(state, target) > self.params.charge_range:
                continue
            building = self.engine.board.hex(target).building is not None
            score = (enemies, 1 if building else 0)
            if best_score is None or score > best_score or (score == best_score and best is not None and lc.id < best.id):
                best = lc
                best_score = score
        return None if best is None else best.id

    def _explode(self, by_action: dict[str, list[LegalCommand]]) -> str:
        """Rule 23.4: a charge that is operable explodes in this phase or never."""
        charges = by_action.get("explode_demo", [])
        if charges:
            return min(charges, key=lambda lc: lc.id).id
        return self._first_of(by_action, ("end_phase",))

    # ---------------------------------------------------------------- rule 22

    def _flamethrower(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        """Rule 22: twenty firepower with no modifier is better than any fire group."""
        return min(
            by_action["ft_fire"],
            key=lambda lc: (-self._occupants(state, lc.command.hex), lc.id),
        ).id

    def _occupants(self, state: State, hex_ref: HexRef | None) -> int:
        if hex_ref is None:
            return 0
        return sum(1 for u in state.infantry_in(hex_ref) if u.player != self.player and visible_to(state, u, self.player))

    # ---------------------------------------------------------------- rule 27

    def _sewer(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str | None:
        """Rule 27.2: go down when the entrance on the other end is nearer the objective."""
        best: LegalCommand | None = None
        best_gain: int | None = None
        for lc in by_action.get("sewer_move", []):
            start = state.units[lc.command.units[0]].hex
            target = lc.command.hex
            if start is None or target is None:
                continue
            gain = self._distance(start) - self._distance(target)
            if gain <= 0:
                continue
            if best_gain is None or gain > best_gain or (gain == best_gain and best is not None and lc.id < best.id):
                best = lc
                best_gain = gain
        return None if best is None else best.id

    def _sewer_return(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        """Rule 27.22: this player names where the stack of the other side comes up."""
        returns = by_action.get("sewer_return", [])
        if not returns:
            return self._first_of(by_action, ("end_phase",))
        return max(returns, key=lambda lc: (self._own_distance(lc.command.hex), -ord(lc.id[0]))).id

    def _own_distance(self, hex_ref: HexRef | None) -> int:
        """How far the hex is from the objectives of this agent, which is what it wants."""
        return 0 if hex_ref is None else self._distance(hex_ref)

    # ---------------------------------------------------------------- rule 25

    def _conceal(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        """Rule 25.6 and 25.7: some counters go on the stacks, and some go on empty hexes."""
        placed = sum(1 for c in state.concealment if c.player == self.player)
        own_hexes = {u.hex for u in state.player_units(self.player) if u.hex is not None}
        covered = {c.hex for c in state.concealment}
        with_units = [lc for lc in by_action["place_concealment"] if lc.command.hex in own_hexes]
        fresh = [lc for lc in with_units if lc.command.hex not in covered]
        if fresh:
            return min(fresh, key=lambda lc: lc.id).id
        # Each stack of this side has a counter, so each counter that is left is a choice
        # between a dummy on an empty hex and a second counter over a stack (rule 25.7).
        # A dummy near the enemy is the one the other player must look at, and a second
        # counter over a stack makes that stack look larger.
        empty = [
            lc
            for lc in by_action["place_concealment"]
            if lc.command.hex not in own_hexes and lc.command.hex not in covered
        ]
        doubles = [lc for lc in with_units]
        want_dummy = placed % 10 < self.params.dummy_share
        if empty and (want_dummy or not doubles):
            return min(empty, key=lambda lc: (self._enemy_distance(state, lc.command.hex), lc.id)).id
        if doubles:
            return min(doubles, key=lambda lc: (self._enemy_distance(state, lc.command.hex), lc.id)).id
        return min(by_action["place_concealment"], key=lambda lc: lc.id).id

    # ----------------------------------------------------------------- shared

    def _enemy_distance(self, state: State, hex_ref: HexRef | None) -> int:
        if hex_ref is None:
            return 99
        enemies = r10_resolution.enemy_occupied_hexes(state, self.player)
        if not enemies:
            return 99
        return min(geometry.distance(hex_ref, h) for h in enemies)


def with_parameters(**changes: object) -> Parameters:
    """A parameter record for a named variant of the agent, for the league."""
    return replace(Parameters(), **changes)
