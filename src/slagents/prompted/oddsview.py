"""The odds in the text view (FR-45): each command with what the tables say it does.

A model that reads a text board has no fire table in its head. The first gauntlet of a
local model (2026-09-19) lost 16 of 16 to the scripted agents, and the scripted agents
read the odds of the core. This module gives the prompt the same numbers: for a fire
command, the chance that the shot gets a result and the chance that each unit in the
target breaks; for a move, the chance that the mover breaks under the fire that can reach
it; for a close combat, the kill chance of each side; for a rally, the chance it holds.
The numbers come from `slagents.scripted.odds`, the module the doctrine agent reads, so a
number in the prompt is the number the tables give and no rule is written here.

The view reads only what the acting player can see (SR-09, AR-09). The odds of a shot name
the units in the target hex, so a shot at a hex below a concealment counter has no odds in
the text, and the loss of a hex counts the enemy units the player sees and no other. The
prompt tells the model as much, so it reads a missing number as unknown and not as zero.
"""

from __future__ import annotations

from typing import Any

from slagents.scripted import odds
from slcore import geometry
from slcore.engine import Engine
from slcore.frame import LegalCommand
from slcore.game import PHASE_MOVEMENT, FireGroup, State
from slcore.geometry import HexRef
from slcore.los_eval import evaluate as evaluate_los
from slcore.rules import r08_fire, r14_rally, r15_leadership, r20_close_combat, r26_fanaticism, victory
from slcore.rules.r12_morale import morale_value
from slcore.units import KIND_LEADER, KIND_SW, Unit
from slcore.view import visible_to

# A shot at a track hex reads at most this many of our shooters, the strongest first.
RETURN_GROUP_SIZE = 4
# The odds of a shot name at most this many units of the target, the most likely first.
BREAKS_NAMED = 4

CONCEALED_TARGET = "target below a concealment counter, odds unknown"
NO_ENEMY_FIRE = "no visible enemy can fire at it"


def percent(count: int, whole: int = odds.ONE) -> int:
    """A count out of `whole` as a whole percent, rounded to the nearest."""
    return (count * 100 + whole // 2) // whole


class OddsView:
    """The odds of one decision, from the acting player's view of the state."""

    def __init__(self, engine: Engine, state: State, viewer: int) -> None:
        self.engine = engine
        self.state = state
        self.viewer = viewer
        self.opponent = 1 - viewer
        self.enemies = [u for u in state.player_units(self.opponent) if u.hex is not None and visible_to(state, u, viewer)]
        self._groups: dict[HexRef, list[odds.EnemyGroup]] = {}
        self._loss: dict[tuple[HexRef, bool, str, bool], int | None] = {}

    # ------------------------------------------------------------------ the loss

    def groups_at(self, dst: HexRef) -> list[odds.EnemyGroup]:
        found = self._groups.get(dst)
        if found is None:
            found = odds.enemy_groups(self.engine, self.state, dst, self.enemies)
            self._groups[dst] = found
        return found

    def loss(self, unit: Unit, dst: HexRef, moving: bool) -> int | None:
        """The chance out of `odds.ONE` that the unit breaks or dies in `dst` under the
        worst visible enemy group, or None when no visible enemy can fire at the hex."""
        key = (dst, moving, unit.type_key, unit.broken)
        if key in self._loss:
            return self._loss[key]
        groups = self.groups_at(dst)
        chance = odds.loss(self.engine, self.state, unit, dst, moving, groups) if groups else None
        self._loss[key] = chance
        return chance

    def exposure(self, unit: Unit, dst: HexRef | None, moving: bool) -> int | None:
        """The worst hex of the track and the destination in the Movement Phase, because
        rule 16.1 lets the defender fire at any hex of the track. In another phase, the
        destination alone, under the prep fire of the next enemy turn."""
        hexes: list[HexRef] = []
        in_movement = self.state.phase == PHASE_MOVEMENT and (moving or unit.moved)
        if in_movement:
            hexes.extend(unit.track)
        if dst is not None:
            hexes.append(dst)
        worst: int | None = None
        for h in hexes:
            chance = self.loss(unit, h, in_movement)
            if chance is not None and (worst is None or chance > worst):
                worst = chance
        return worst

    # ------------------------------------------------------------------ the shot

    def target_visible(self, target: HexRef) -> bool:
        """Each enemy unit in the hex is in the player's view, so the odds may name it."""
        return all(visible_to(self.state, u, self.viewer) for u in self.state.infantry_in(target) if u.player == self.opponent and not u.eliminated)

    def shot_text(self, group: FireGroup, state: State | None = None) -> str:
        """The odds of a fire group at its target, in this phase, as the prompt says them."""
        if not self.target_visible(group.target):
            return CONCEALED_TARGET
        result = odds.shot(self.engine, state or self.state, group, self.state.phase)
        if result.halves <= 0:
            return "no firepower at that range"
        if not result.breaks and result.effect == 0:
            return f"firepower {result.firepower} at {result.drm:+d}: no result possible"
        named = sorted(result.breaks.items(), key=lambda item: (-item[1], item[0]))[:BREAKS_NAMED]
        breaks = " ".join(f"unit {uid} {percent(chance)}%" for uid, chance in named)
        return f"firepower {result.firepower} at {result.drm:+d}: result {percent(result.effect)}%, kill {percent(result.kia)}%, break {breaks}"

    def _return_text(self, lc: LegalCommand) -> str:
        """Rule 16.1: the movers stand in the track hex for the fire of our best group there."""
        track_hex = lc.command.hex
        if track_hex is None:
            return ""
        movers = {uid: self.state.units[uid].with_(hex=track_hex, returned_from=self.state.units[uid].hex) for uid in lc.command.units}
        hypothetical = self.state.with_units(movers)
        types = self.engine.types
        able: list[tuple[int, int, int, tuple[int, int | None]]] = []
        for unit in self.state.player_units(self.viewer):
            if unit.hex is None or unit.broken or unit.kind == KIND_LEADER or unit.is_vehicle:
                continue
            if not evaluate_los(self.engine.board, self.engine.los, unit.hex, track_hex).clear:
                continue
            for weapon in (None,) + tuple(w for w in self.state.carried_by(unit.id) if w.kind == KIND_SW and not w.broken and not w.malfunction):
                fire = r08_fire.member_firepower(hypothetical, types, unit, weapon, track_hex, unit.moved)
                if fire is not None:
                    weapon_id = None if weapon is None else weapon.id
                    able.append((-fire.halves, unit.id, -1 if weapon_id is None else weapon_id, (unit.id, weapon_id)))
        if not able:
            return f"movers put back in {self.terrain(track_hex)}: no shooter of yours reaches it"
        able.sort()
        members = tuple(item[3] for item in able[:RETURN_GROUP_SIZE])
        return f"movers put back in {self.terrain(track_hex)}, your best group there: " + self.shot_text(FireGroup(track_hex, members, None), hypothetical)

    # ------------------------------------------------------------ the other odds

    def _close_combat_text(self, lc: LegalCommand) -> str:
        """Rule 20.3: the kill chance of the attack and of the answer, each out of 36."""
        extra = dict(lc.command.extra)
        attackers = tuple(lc.command.units)
        targets = tuple(int(t) for t in extra.get("targets", ()))
        if not attackers or not targets:
            return ""
        leader = extra.get("leader")
        ours = self._kill_ways(attackers, targets, None if leader is None else int(leader))
        unbroken = tuple(t for t in targets if not self.state.units[t].broken)
        if not unbroken:
            return f"kill {percent(ours, odds.WAYS)}%, the targets are broken and fight back with nothing"
        theirs = self._kill_ways(unbroken, attackers, self._best_leader(unbroken))
        return f"kill {percent(ours, odds.WAYS)}%, their answer kills {percent(theirs, odds.WAYS)}%"

    def _kill_ways(self, attackers: tuple[int, ...], targets: tuple[int, ...], leader: int | None) -> int:
        types = self.engine.types
        attack = r20_close_combat.firepower(self.state, types, attackers, attacking=True)
        defense = r20_close_combat.firepower(self.state, types, targets, attacking=False)
        row = self.engine.tables.cc.odds_row(attack, defense)
        modifier = types[self.state.units[leader].type_key].leadership if leader is not None else 0
        return sum(count for roll, count in odds.DICE_WAYS.items() if roll + modifier <= row.kill)

    def _best_leader(self, unit_ids: tuple[int, ...]) -> int | None:
        leaders = [uid for uid in unit_ids if self.state.units[uid].kind == KIND_LEADER]
        if not leaders:
            return None
        return min(leaders, key=lambda uid: self.engine.types[self.state.units[uid].type_key].leadership)

    def _rally_text(self, unit: Unit) -> str:
        """Rule 14.2 with the desperation of 14.6: the rolls of 36 that rally the unit, less
        the roll of 18.3 that removes it."""
        types = self.engine.types
        modifier, _ = r15_leadership.modifier_for_check(self.state, types, unit)
        modifier += r26_fanaticism.modifier_for(self.state, unit)
        target = morale_value(types, unit) - (r14_rally.DESPERATION_PENALTY if unit.dm else 0)
        ways = sum(count for roll, count in odds.DICE_WAYS.items() if roll + modifier <= target and roll != r14_rally.SELF_CASUALTY_ROLL)
        return f"rally {percent(ways, odds.WAYS)}%"

    # ------------------------------------------------------------------ the text

    def terrain(self, hex_ref: HexRef) -> str:
        """The terrain of a hex in words, with the building it is part of."""
        h = self.engine.board.hex(hex_ref)
        return h.terrain.replace("_", " ") + (f" {h.building.id}" if h.building is not None else "")

    def _move_text(self, lc: LegalCommand, moving: bool) -> str:
        dst = lc.command.hex
        if dst is None:
            return ""
        worst: int | None = None
        for uid in lc.command.units:
            chance = self.exposure(self.state.units[uid], dst, moving)
            if chance is not None and (worst is None or chance > worst):
                worst = chance
        where = self.terrain(dst)
        if worst is None:
            return f"{where}, {NO_ENEMY_FIRE}"
        return f"{where}, break chance {percent(worst)}%"

    def command_note(self, lc: LegalCommand) -> str:
        """The odds of one legal command, or an empty text for a command with none."""
        action = lc.command.action
        fg = self.state.fire_group
        if action in ("group_add", "group_add_weapon"):
            target = lc.command.hex
            if target is None:
                return ""
            member = (lc.command.units[0], lc.command.weapon)
            if fg is not None and fg.target == target:
                trial = FireGroup(target, fg.members + (member,), fg.leader)
                return f"group of {len(trial.members)}: " + self.shot_text(trial)
            return self.shot_text(FireGroup(target, (member,), None))
        if action == "group_leader" and fg is not None:
            return "with the leader: " + self.shot_text(FireGroup(fg.target, fg.members, lc.command.units[0]))
        if action == "group_fire" and fg is not None:
            return "fire now: " + self.shot_text(fg)
        if action == "track_return":
            return self._return_text(lc)
        if action in ("move", "stack_move"):
            return self._move_text(lc, moving=True)
        if action in ("advance", "rout"):
            return self._move_text(lc, moving=False)
        if action == "cc_attack":
            return self._close_combat_text(lc)
        if action == "rally" and lc.command.units:
            return self._rally_text(self.state.units[lc.command.units[0]])
        if action == "stay" and lc.command.units:
            return self.unit_note(self.state.units[lc.command.units[0]])
        return ""

    def unit_note(self, unit: Unit) -> str:
        """The break chance of a unit where it stands, under the visible enemy fire."""
        if unit.hex is None or unit.is_vehicle or unit.kind == KIND_SW:
            return ""
        moving = self.state.phase == PHASE_MOVEMENT and unit.moved
        chance = self.exposure(unit, unit.hex, moving) if moving else self.loss(unit, unit.hex, False)
        if chance is None:
            return NO_ENEMY_FIRE
        return f"break chance here {percent(chance)}%"


def objective_lines(engine: Engine, state: State, viewer: int) -> list[str]:
    """The victory conditions of the scenario card, with the buildings they name.

    The card is public, so each side reads the whole of it. The standing of a condition
    is not here: it counts units the player may not see (AR-09), and the model reads the
    buildings it holds from the unit list.
    """
    scenario = engine.scenario
    board = engine.board
    side = scenario.players()[viewer]
    lines = [f"Victory conditions, for the {side} side to read as its own or as the enemy's:"]
    by_building = victory.buildings_on(board)

    def named(group_ids: Any) -> str:
        parts = []
        for building in victory.group_buildings(scenario, board, group_ids):
            hexes = ", ".join(geometry.hex_id(*h) for h in by_building.get(building, ()))
            parts.append(f"{building} ({hexes})")
        return "; ".join(parts) if parts else "none"

    for condition in scenario.victory:
        params = dict(condition.params)
        note = str(params.get("note", "")).strip()
        owner = str(params.get("side", ""))
        text = f"  {owner or 'either'} side, {condition.kind}: {note}" if note else f"  {owner or 'either'} side, {condition.kind}"
        lines.append(text)
        if condition.kind == victory.KIND_BUILDING_SWING:
            lines.append(f"    buildings of the {owner} side: {named(params.get('own_groups', []))}")
            lines.append(f"    buildings of the other side: {named(params.get('enemy_groups', []))}")
    lines.append(f"  The game ends after turn {state.turn_limit}.")
    return lines
