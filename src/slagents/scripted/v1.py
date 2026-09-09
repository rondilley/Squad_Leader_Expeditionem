"""Scripted agent v1: fire at the best odds, move to cover and the objective, rout to cover.

Parameters have names (FR-44) and the agent is deterministic for a state and a frame.
It is the constant opponent of the learning ladder, so its version is recorded with
each result.
"""

from __future__ import annotations

from dataclasses import dataclass

from slcore import geometry
from slcore.engine import Engine
from slcore.frame import DecisionFrame, LegalCommand
from slcore.game import (
    PHASE_ADVANCE,
    PHASE_ADVANCING_FIRE,
    PHASE_CLOSE_COMBAT,
    PHASE_DEFENSIVE_FIRE,
    PHASE_MOVEMENT,
    PHASE_PREP_FIRE,
    PHASE_RALLY,
    PHASE_ROUT,
    PHASE_SETUP,
    State,
)
from slcore.geometry import HexRef
from slcore.rules import r06_stacking, r08_fire, r11_terrain
from slcore.rules.r13_rout import is_cover
from slcore.units import KIND_SW


@dataclass(frozen=True)
class Parameters:
    """The named parameters of the agent."""

    aggression: int = 2
    cover_preference: int = 3
    fire_priority: int = 2
    group_size: int = 3
    advance_into_close_combat: bool = True


class ScriptedV1:
    name = "scripted"
    version = "1"

    def __init__(self, engine: Engine, player: int, params: Parameters | None = None) -> None:
        self.engine = engine
        self.player = player
        self.params = params or Parameters()
        self.objectives: tuple[HexRef, ...] = engine.objectives(player)

    # ------------------------------------------------------------- selection

    def select(self, state: State, frame: DecisionFrame) -> str:
        if not frame.commands:
            raise ValueError("no legal command")
        by_action: dict[str, list[LegalCommand]] = {}
        for lc in frame.commands:
            by_action.setdefault(lc.command.action, []).append(lc)
        phase = frame.phase
        if phase == PHASE_SETUP:
            return self._setup(state, by_action)
        if phase == PHASE_RALLY:
            return self._first_of(by_action, ("repair", "rally", "end_phase"))
        if phase in (PHASE_PREP_FIRE, PHASE_DEFENSIVE_FIRE, PHASE_ADVANCING_FIRE):
            return self._fire(state, frame, by_action)
        if phase == PHASE_MOVEMENT:
            return self._move(state, by_action)
        if phase == PHASE_ROUT:
            return self._rout(state, by_action)
        if phase == PHASE_ADVANCE:
            return self._advance(state, by_action)
        if phase == PHASE_CLOSE_COMBAT:
            return self._close_combat(state, by_action)
        return self._first_of(by_action, ("end_phase",))

    def _setup(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        """Rule 21.2: the carriers go down first, then the weapons go to the carriers.

        A support weapon that goes on the board before a carrier stays on the ground for
        the whole game, because a placed weapon is no longer waiting for a place. The
        flamethrower and the demolition charge of rule 22 and rule 23 are the reason this
        is worth a rule of its own: a group that leaves them on the ground gives up the
        rules it was built for.
        """
        if "place_weapon" in by_action:
            return min(by_action["place_weapon"], key=lambda lc: lc.id).id
        carriers = [
            lc
            for lc in by_action.get("place", [])
            if state.units[lc.command.units[0]].kind != KIND_SW
        ]
        if carriers:
            return min(carriers, key=lambda lc: lc.id).id
        if "place_concealment" in by_action:
            # After the units, because a counter over a stack hides that stack (rule 25.2)
            # and there is no stack to hide before the units are on the board.
            return self._conceal(state, by_action)
        return self._first_of(by_action, ("place", "end_setup"))

    def _conceal(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        """Rule 25.6: a counter goes over a stack of this side, and then anywhere allowed.

        A counter over a stack hides that stack from the other player (rule 25.2). A
        counter on a hex that already has one adds nothing that this agent can use, so the
        agent covers each of its own hexes first.
        """
        own = {u.hex for u in state.player_units(self.player) if u.hex is not None}
        covered = {c.hex for c in state.concealment if c.player == self.player}
        fresh = [lc for lc in by_action["place_concealment"] if lc.command.hex in own and lc.command.hex not in covered]
        if fresh:
            return min(fresh, key=lambda lc: lc.id).id
        return min(by_action["place_concealment"], key=lambda lc: lc.id).id

    def _first_of(self, by_action: dict[str, list[LegalCommand]], actions: tuple[str, ...]) -> str:
        for action in actions:
            if action in by_action:
                return min(by_action[action], key=lambda lc: lc.id).id
        return min((lc for group in by_action.values() for lc in group), key=lambda lc: lc.id).id

    # ------------------------------------------------------------------ fire

    def _fire(self, state: State, frame: DecisionFrame, by_action: dict[str, list[LegalCommand]]) -> str:
        group = state.fire_group
        if group is None:
            best = self._best_target(state, by_action)
            if best is not None:
                return best
            return self._first_of(by_action, ("track_return", "end_phase"))
        if "group_add_weapon" in by_action or "group_add" in by_action:
            if len(group.members) < self.params.group_size:
                same = [lc for lc in by_action.get("group_add_weapon", []) + by_action.get("group_add", []) if lc.command.hex == group.target]
                if same:
                    return min(same, key=lambda lc: (-self._member_value(state, lc, group.target), lc.id)).id
        if "group_leader" in by_action:
            return min(by_action["group_leader"], key=lambda lc: (self.engine.types[state.units[lc.command.units[0]].type_key].leadership, lc.id)).id
        return self._first_of(by_action, ("group_fire", "end_phase"))

    def _best_target(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str | None:
        adds = by_action.get("group_add_weapon", []) + by_action.get("group_add", [])
        if not adds:
            return None
        best: LegalCommand | None = None
        best_score = None
        for lc in adds:
            target = lc.command.hex
            if target is None:
                continue
            score = self._target_score(state, lc, target)
            if best_score is None or score > best_score or (score == best_score and best is not None and lc.id < best.id):
                best = lc
                best_score = score
        return None if best is None else best.id

    def _target_score(self, state: State, lc: LegalCommand, target: HexRef) -> tuple[int, int, int]:
        """Odds first: firepower against the target, then the terrain, then the count."""
        halves = self._member_value(state, lc, target)
        modifier = r11_terrain.target_hex_modifier(self.engine.board, target)
        occupants = sum(1 for u in state.infantry_in(target) if u.player != self.player and not u.broken)
        return (halves * self.params.fire_priority - modifier * 2, occupants, -modifier)

    def _member_value(self, state: State, lc: LegalCommand, target: HexRef) -> int:
        unit = state.units[lc.command.units[0]]
        weapon = None if lc.command.weapon is None else state.units[lc.command.weapon]
        result = r08_fire.member_firepower(state, self.engine.types, unit, weapon, target, unit.moved)
        return 0 if result is None else result.halves

    # -------------------------------------------------------------- movement

    def _move(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        best: LegalCommand | None = None
        best_score: tuple[int, int] | None = None
        for action in ("stack_move", "move"):
            for lc in by_action.get(action, []):
                unit = state.units[lc.command.units[0]]
                dst = lc.command.hex
                if unit.hex is None or dst is None:
                    continue
                gain = self._distance(unit.hex) - self._distance(dst)
                cover = self.params.cover_preference if is_cover(self.engine.board, dst) else 0
                score = (gain * self.params.aggression + cover, len(lc.command.units))
                if best_score is None or score > best_score or (score == best_score and best is not None and lc.id < best.id):
                    best = lc
                    best_score = score
        if best is not None and best_score is not None and best_score[0] > 0:
            return best.id
        if "end_phase" in by_action:
            return by_action["end_phase"][0].id
        return self._relief(state, by_action, best)

    def _relief(self, state: State, by_action: dict[str, list[LegalCommand]], best: LegalCommand | None) -> str:
        """Rule 6.3: the phase cannot end while a hex is over a limit, so a unit must leave.

        The command that pays for the relief is a move out of that hex. A move somewhere
        else does not relieve it, and the window opens again with the same problem. A
        pickup or a drop does not help either, because rule 6.2 counts the portage of a hex
        and not the portage of a carrier, so a weapon on the ground of that hex still
        counts. An agent that answers this window with a pickup and then a drop does not
        stop.
        """
        over = set(r06_stacking.overstacked_hexes(state, self.engine.types, self.player))
        # Sewer movement is a move out of the hex as well (rule 27.2), and the core counts
        # it as one when it decides whether this window can close.
        moves = by_action.get("stack_move", []) + by_action.get("move", []) + by_action.get("sewer_move", [])
        out_of_the_hex = [
            lc for lc in moves if any(state.units[uid].hex in over for uid in lc.command.units)
        ]
        if out_of_the_hex:
            return min(out_of_the_hex, key=lambda lc: (-len(lc.command.units), lc.id)).id
        if moves:
            return min(moves, key=lambda lc: (-len(lc.command.units), lc.id)).id
        if best is not None:
            return best.id
        return min((lc for group in by_action.values() for lc in group), key=lambda lc: lc.id).id

    def _distance(self, hex_ref: HexRef) -> int:
        if not self.objectives:
            return 0
        return min(geometry.distance(hex_ref, o) for o in self.objectives)

    def _rout(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        routs = by_action.get("rout", [])
        if routs:
            return min(routs, key=lambda lc: (self._distance(lc.command.hex) if lc.command.hex else 0, lc.id)).id
        return self._first_of(by_action, ("stay", "end_phase"))

    def _advance(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        best: LegalCommand | None = None
        best_score: tuple[int, int] | None = None
        for lc in by_action.get("advance", []):
            unit = state.units[lc.command.units[0]]
            dst = lc.command.hex
            if unit.hex is None or dst is None:
                continue
            enemies = sum(1 for u in state.infantry_in(dst) if u.player != self.player and not u.broken)
            if enemies and not self.params.advance_into_close_combat:
                continue
            gain = self._distance(unit.hex) - self._distance(dst)
            cover = self.params.cover_preference if is_cover(self.engine.board, dst) else 0
            score = (gain * self.params.aggression + cover + enemies * self.params.aggression, -enemies)
            if best_score is None or score > best_score or (score == best_score and best is not None and lc.id < best.id):
                best = lc
                best_score = score
        if best is not None and best_score is not None and best_score[0] > 0:
            return best.id
        return self._first_of(by_action, ("end_phase",))

    def _close_combat(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        attacks = by_action.get("cc_attack", [])
        if not attacks:
            return self._first_of(by_action, ("end_phase",))
        best = max(attacks, key=lambda lc: (len(lc.command.units), 1 if dict(lc.command.extra).get("leader") is not None else 0, -len(dict(lc.command.extra).get("targets", []))))
        return best.id
