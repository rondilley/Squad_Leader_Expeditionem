"""What the host adds to a frame so a person can read it: names, labels, hexes, and odds.

The client holds no rule (AR-06). So the host names each unit, writes the label of each
legal command, gives the hexes each command touches (for the selection on the board),
and gives the odds of the command from `slagents.scripted.odds` in the view of the side
that acts. The odds of a shot at a hex below a concealment counter are not given, because
they would name what the counter hides (SR-09, AR-09).

A unit name is the type of the counter and a short number for each side, with the hex:
"4-4-7 #3 (D4)". A leader has its own name: "9-1 Lt Dubovich (D4)". The number is the
order of the unit among the units of the same type of its side, so it does not change in
a game. The view already holds the unit ID, so the number shows nothing new.

The texts here are the project's own words. There is no rulebook text in this module.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from slcore import geometry
from slcore.engine import Engine
from slcore.frame import DecisionFrame, LegalCommand
from slcore.game import FireGroup, State
from slcore.units import KIND_LEADER, KIND_SW, Unit
from slcore.view import SPECTATOR, visible_to

# A short text for each phase, in the project's words, for the phase strip of a client.
PHASE_TEXT: dict[str, str] = {
    "setup": "Put your counters in the set up area that the scenario gives your side.",
    "rally": "Try to rally broken units and repair broken weapons.",
    "prep_fire": "The side that moves fires first. A unit that fires now cannot move this turn.",
    "movement": "Move units. The other side can fire at each hex a unit goes through.",
    "defensive_fire": "The side that does not move fires at the units that moved or stayed.",
    "advancing_fire": "Units that did not fire in the prep fire phase fire now, at less strength.",
    "rout": "Broken units go back to cover, away from the enemy.",
    "advance": "Units move one hex, also into a hex with an enemy unit.",
    "close_combat": "Units in the same hex as an enemy unit fight at close range.",
    "end": "The turn ends.",
    "game_over": "The game is over.",
}

# A short text for each window sub-step, which is what the side that acts decides now.
# The key is "phase/sub-step", as a frame names them (`slcore.phases.PHASE_STEPS`). A
# phase with one window keeps the text of the phase.
STEP_TEXT: dict[str, str] = {
    "setup/place": PHASE_TEXT["setup"],
    "rally/rally_window": PHASE_TEXT["rally"],
    "prep_fire/smoke_window": "Put smoke from the units that carry it before the fire of this phase.",
    "prep_fire/fire_window": PHASE_TEXT["prep_fire"],
    "movement/sewer_return": "Say where the enemy units lost in the sewer come up.",
    "movement/move_window": PHASE_TEXT["movement"],
    "defensive_fire/fire_window": PHASE_TEXT["defensive_fire"],
    "defensive_fire/push_out": "Move each of your units below an enemy vehicle to an adjacent hex of your choice.",
    "advancing_fire/demo_window": "Set off the demolition charges that your units placed.",
    "advancing_fire/fire_window": PHASE_TEXT["advancing_fire"],
    "rout/rout_window": PHASE_TEXT["rout"],
    "advance/advance_window": PHASE_TEXT["advance"],
    "close_combat/cc_declare": "Say which of your units attack which enemy units in close combat.",
}


def fire_group_text(state: State) -> str | None:
    """The text for the side that builds a fire group (rule 8.4): the group fires only
    when that side resolves it, so the text says how. None with no fire group."""
    group = state.fire_group
    if group is None:
        return None
    target = geometry.hex_id(*group.target)
    return f"Your fire group aims at {target}. Add more units to it, or click {target} (or 'resolve the fire group') to fire."


def phase_text(phase: str, sub_step: str = "") -> str:
    """The text for the phase strip: the text of the sub-step, else of the phase."""
    if sub_step == "game_over":
        return PHASE_TEXT["game_over"]
    return STEP_TEXT.get(f"{phase}/{sub_step}", PHASE_TEXT.get(phase, ""))


# A facing or a direction index as a compass word, the same words as the log text.
FACING_TEXT = ("north", "north-east", "south-east", "south", "south-west", "north-west")
AMMO_TEXT = {"ap": "an armour-piercing", "he": "a high explosive", "heat": "a HEAT", "canister": "a canister"}
ARMAMENT_TEXT = {"main": "the main armament", "mg": "the machine guns"}


def facing_text(value: object) -> str:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < len(FACING_TEXT):
        return FACING_TEXT[value]
    return str(value)


PHASE_ORDER = (
    "setup",
    "rally",
    "prep_fire",
    "movement",
    "defensive_fire",
    "advancing_fire",
    "rout",
    "advance",
    "close_combat",
)

UNKNOWN_UNIT = "unknown unit"
# The side keys of a scenario that name no army. Such a side takes the name of its army.
GENERIC_SIDES = frozenset({"allied", "axis", "attacker", "defender"})
PLAYER_TEXT = re.compile(r"\bplayer ([01])\b")
SIDE_KEYS = ("player", "phasing", "winner", "side")
FIRE_ACTIONS = ("group_add", "group_add_weapon", "group_leader", "group_fire")


def side_names(engine: Engine) -> dict[int, str]:
    """The side name of each player, such as "Russian".

    A scenario of the library names its sides `allied` and `axis`, and its card names the
    armies. Such a side gets the name of its army (or armies), so the windows, the log, and
    the end of the game use the names of the card.
    """
    scenario = engine.scenario
    out: dict[int, str] = {}
    for index, name in enumerate(scenario.players()):
        armies = scenario.side_spec(name).armies()
        if name in GENERIC_SIDES and armies:
            out[index] = " and ".join(army.replace("_", " ").title() for army in armies)
        else:
            out[index] = name.replace("_", " ").title()
    return out


def type_text(unit_type_key: str) -> str:
    """The printed type of a counter: "russian:4-4-7" gives "4-4-7"."""
    return unit_type_key.split(":", 1)[-1]


class Names:
    """The name of each unit of one game. The numbers follow the unit IDs."""

    def __init__(self) -> None:
        self._count = -1
        self._base: dict[int, str] = {}

    def _build(self, state: State) -> None:
        counts: dict[tuple[int, str], int] = {}
        base: dict[int, str] = {}
        for unit in sorted(state.units, key=lambda u: u.id):
            text = type_text(unit.type_key)
            if unit.kind == KIND_LEADER and unit.name:
                base[unit.id] = f"{text} {unit.name}"
                continue
            key = (unit.player, unit.type_key)
            counts[key] = counts.get(key, 0) + 1
            base[unit.id] = f"{text} #{counts[key]}"
        self._base = base
        self._count = len(state.units)

    def base(self, state: State, unit_id: int) -> str:
        if self._count != len(state.units):
            self._build(state)
        return self._base.get(unit_id, f"unit {unit_id}")

    def full(self, state: State, unit_id: int) -> str:
        """The name with the hex where the counter is now: "4-4-7 #3 (D4)"."""
        if unit_id < 0 or unit_id >= len(state.units):
            return f"unit {unit_id}"
        unit = state.units[unit_id]
        where = unit.hex
        if where is None and unit.carrier is not None:
            where = state.units[unit.carrier].hex
        if where is None and unit.passenger_of is not None:
            where = state.units[unit.passenger_of].hex
        text = self.base(state, unit_id)
        return f"{text} ({geometry.hex_id(*where)})" if where is not None else text

    def for_viewer(self, state: State, unit_id: int, viewer: int) -> str:
        """The name a viewer may read. A unit the viewer cannot see has no name."""
        if unit_id < 0 or unit_id >= len(state.units):
            return UNKNOWN_UNIT
        unit = state.units[unit_id]
        if viewer != SPECTATOR and unit.player != viewer and not unit.eliminated and not visible_to(state, unit, viewer):
            return UNKNOWN_UNIT
        return self.full(state, unit_id)


# ------------------------------------------------------------------ log lines

# The kinds of line where `target` is a unit (the vehicle that was hit), and not a hex or
# the number that the dice must reach.
KILL_TARGET_KINDS = ("kill_roll",)
_UNIT_KEYS = frozenset({"unit", "weapon", "leader", "carrier", "vehicle", "placer"})
_UNIT_LIST_KEYS = frozenset({"units", "attackers", "targets"})


def named_ids(value: Any, found: list[int]) -> None:
    """The unit IDs a log line names, as `slcore.view` finds them."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _UNIT_KEYS and isinstance(item, int):
                found.append(item)
            elif key in _UNIT_LIST_KEYS and isinstance(item, list):
                for one in item:
                    if isinstance(one, int):
                        found.append(one)
                    else:
                        named_ids(one, found)
            else:
                named_ids(item, found)
    elif isinstance(value, list):
        for item in value:
            named_ids(item, found)


def with_side_names(text: str, sides: Mapping[int, str]) -> str:
    """"player 0" in a core text becomes the side name, such as "Russian"."""
    return PLAYER_TEXT.sub(lambda m: sides.get(int(m.group(1)), m.group(0)), text)


def dress_line(entry: dict[str, Any], state: State, names: Names, viewer: int, sides: Mapping[int, str]) -> dict[str, Any]:
    """A log line with the unit names and the side names it needs (slice 8)."""
    out = dict(entry)
    data = entry.get("data") or {}
    ids: list[int] = []
    named_ids(data, ids)
    # The fields that name a unit in only some kinds of line: the crew of a vehicle, a
    # demolition charge, the wrecks a vehicle pushed, and the vehicle a kill roll reads. `for_viewer` still hides a
    # unit the viewer cannot see.
    for key in ("crew", "charge"):
        if isinstance(data.get(key), int) and not isinstance(data.get(key), bool):
            ids.append(int(data[key]))
    for one in data.get("wrecks") or ():
        if isinstance(one, int) and not isinstance(one, bool):
            ids.append(one)
    if entry.get("kind") in KILL_TARGET_KINDS and isinstance(data.get("target"), int):
        ids.append(int(data["target"]))
    if ids:
        out["names"] = {str(uid): names.for_viewer(state, uid, viewer) for uid in dict.fromkeys(ids)}
    if any(isinstance(data.get(key), int) for key in SIDE_KEYS) or "cause" in data:
        out["sides"] = {str(k): v for k, v in sides.items()}
    cause = data.get("cause")
    if isinstance(cause, str):
        out["data"] = {**data, "cause": with_side_names(cause, sides)}
    return out


# -------------------------------------------------------------- legal entries


def command_hexes(state: State, lc: LegalCommand, viewer: int) -> list[str]:
    """The hexes a command touches, so a client can offer it on the board."""
    command = lc.command
    out: list[str] = []
    if command.hex is not None:
        out.append(geometry.hex_id(*command.hex))
    extra = dict(command.extra)
    if command.action == "group_fire" and state.fire_group is not None:
        out.append(geometry.hex_id(*state.fire_group.target))
    if command.action == "cc_attack":
        for target in extra.get("targets", ()) or ():
            if isinstance(target, int) and 0 <= target < len(state.units):
                unit = state.units[target]
                if unit.hex is not None and (unit.player == viewer or visible_to(state, unit, viewer)):
                    out.append(geometry.hex_id(*unit.hex))
    if not out and command.units and command.action not in ("end_phase", "end_setup"):
        first = command.units[0]
        if 0 <= first < len(state.units):
            unit = state.units[first]
            where = unit.hex if unit.hex is not None else (state.units[unit.carrier].hex if unit.carrier is not None else None)
            if where is not None:
                out.append(geometry.hex_id(*where))
    if command.weapon is not None and not out:
        weapon = state.units[command.weapon] if 0 <= command.weapon < len(state.units) else None
        if weapon is not None:
            where = weapon.hex if weapon.hex is not None else (state.units[weapon.carrier].hex if weapon.carrier is not None else None)
            if where is not None:
                out.append(geometry.hex_id(*where))
    return list(dict.fromkeys(out))


def _with_weapons(state: State, uid: int, name: Any) -> str:
    """The name of a unit, with the weapons it carries: "6-2-8 (with MMG)"."""
    weapons = [name(w.id) for w in state.carried_by(uid)] if 0 <= uid < len(state.units) else []
    return f"{name(uid)} (with {' and '.join(weapons)})" if weapons else name(uid)


def command_label(
    state: State, lc: LegalCommand, names: Names, viewer: int, blind: frozenset = frozenset()
) -> str:
    """The label of one legal command, with the unit names.

    `blind` is the hexes of the frame where no enemy is known to be (rule 42.4, PR-52). A
    shot at one of them is a shot in the blind, and the label says so.
    """
    command = lc.command
    payload = lc.payload
    extra = dict(command.extra)

    def name(uid: int) -> str:
        return names.for_viewer(state, uid, viewer)

    who = " and ".join(name(uid) for uid in command.units)
    if command.action in ("move", "stack_move", "advance"):
        # Rule 5.7: a carried weapon goes with its carrier, so the label names it.
        who = " and ".join(_with_weapons(state, uid, name) for uid in command.units)
    where = payload.get("hex", "")
    weapon = name(command.weapon) if command.weapon is not None else ""
    action = command.action
    at = "blind into" if command.hex is not None and command.hex in blind else "at"
    if action == "end_phase":
        return "end the phase"
    if action == "end_setup":
        return "set up is complete"
    if action == "place":
        facing = f", facing {facing_text(extra['facing'])}" if "facing" in extra else ""
        return f"place {who} in {where}{facing}"
    if action == "place_weapon":
        return f"give {weapon} to {who}"
    if action == "move":
        return f"move {who} to {where}"
    if action == "stack_move":
        return f"move the stack {who} to {where}"
    if action == "advance":
        return f"advance {who} to {where}"
    if action == "pickup":
        return f"{who} picks up {weapon}"
    if action == "drop":
        return f"{who} drops {weapon}"
    if action == "rally":
        return f"rally {who}"
    if action == "repair":
        return f"repair {weapon}"
    if action == "rout":
        return f"rout {who} to {where}"
    if action == "stay":
        return f"{who} stays in cover"
    if action == "track_return":
        return f"put {who} back in {where}"
    if action == "group_add":
        return f"{who} fires {at} {where}"
    if action == "group_add_weapon":
        return f"{who} fires {weapon} {at} {where}"
    if action == "group_leader":
        return f"{who} directs the fire group"
    if action == "group_fire":
        target = geometry.hex_id(*state.fire_group.target) if state.fire_group is not None else ""
        return f"resolve the fire group at {target}" if target else "resolve the fire group"
    if action == "cc_attack":
        targets = ", ".join(name(int(t)) for t in extra.get("targets", ()) or ())
        leader = extra.get("leader")
        led = f", led by {name(int(leader))}" if leader is not None else ""
        return f"close combat: {who} attack {targets}{led}"
    if action == "place_concealment":
        return f"put a concealment counter in {where}"
    if action == "place_smoke":
        return f"{who} makes smoke in {where}"
    if action == "place_demo":
        return f"{who} places a charge in {where}"
    if action == "explode_demo":
        return f"set off the charge in {where}"
    if action == "ft_fire":
        return f"{who} fires the flamethrower {at} {where}"
    if action == "sewer_move":
        return f"{who} go through the sewer to {where}"
    if action == "sewer_return":
        return f"the sewer party comes up in {where}"
    if action == "vehicle_move":
        facing = f", facing {facing_text(extra['facing'])}" if "facing" in extra else ""
        return f"drive {who} to {where}{facing}"
    if action == "vehicle_pivot":
        facing = f" to face {facing_text(extra['facing'])}" if "facing" in extra else ""
        return f"turn {who}{facing}"
    if action == "board":
        vehicle = extra.get("vehicle")
        return f"{who} gets on {name(int(vehicle))}" if vehicle is not None else f"{who} gets on"
    if action == "debark":
        return f"{who} gets off to {where}" if where else f"{who} gets off"
    if action == "afv_fire":
        ammo = f" with {AMMO_TEXT.get(str(extra['ammo']), 'a ' + str(extra['ammo']))} round" if "ammo" in extra else ""
        if at != "at":
            return f"{who} fires the main gun{ammo} blind into {where}"
        aim = f" at the {extra['aim']}" if "aim" in extra else ""
        return f"{who} fires the main gun{ammo}{aim} in {where}"
    if action == "afv_mg":
        return f"{who} fires its machine guns {at} {where}"
    if action == "at_fire":
        return f"{who} fires {weapon or 'the anti-tank weapon'} at {where}"
    if action == "afv_attack":
        return f"{who} attacks the vehicle in {where}"
    if action == "cc_afv":
        return f"{who} attacks the vehicle in close combat in {where}"
    if action == "afv_repair":
        armament = ARMAMENT_TEXT.get(str(extra.get("armament", "")), "")
        return f"repair {armament} of {who}" if armament else f"repair {who}"
    if action == "push_wreck":
        return f"{who} pushes the wreck in {where}"
    if action == "afv_smoke":
        return f"{who} fires smoke at {where}"
    if action == "afv_dischargers":
        return f"{who} fires its smoke dischargers"
    if action == "push_out":
        return f"{who} steps out from below the enemy vehicle to {where}"
    return fallback_label(action, who, where)


def fallback_label(action: str, who: str, where: str) -> str:
    """The label of an action that `command_label` does not know. The coverage test in
    tests/host/test_annotate_coverage.py fails for each action of the core that gets it."""
    return f"{action.replace('_', ' ')} {who} {where}".strip()


def blind_hexes(engine: Engine, state: State, player: int) -> frozenset:
    """The hexes a frame of this player offers as a shot in the blind (rule 42.4, PR-52).

    The core reads the same set when it builds the frame. It reads no hidden unit, so
    it names nothing the player does not know.
    """
    return engine._blind_hexes(state, player)


# ----------------------------------------------------------------------- odds


class FrameOdds:
    """The odds of each legal command of one frame, in the view of the side that acts."""

    def __init__(self, engine: Engine, state: State, viewer: int) -> None:
        # The import is here, so a host with the odds option off does not load the agents.
        from slagents.prompted.oddsview import OddsView
        from slagents.scripted import odds

        self.odds = odds
        self.view = OddsView(engine, state, viewer)
        self.engine = engine
        self.state = state

    def _shot(self, group: FireGroup) -> dict[str, Any] | None:
        if not self.view.target_visible(group.target):
            return None
        result = self.odds.shot(self.engine, self.state, group, self.state.phase)
        worst = max(result.breaks.values()) if result.breaks else 0
        return {
            "kind": "fire",
            "firepower": result.firepower,
            "drm": result.drm,
            "result": result.effect,
            "kia": result.kia,
            "break": worst,
            "of": self.odds.ONE,
        }

    def _move(self, lc: LegalCommand, moving: bool) -> dict[str, Any] | None:
        dst = lc.command.hex
        if dst is None:
            return None
        worst: int | None = None
        for uid in lc.command.units:
            unit = self.state.units[uid]
            if unit.is_vehicle or unit.kind == KIND_SW:
                continue
            chance = self.view.exposure(unit, dst, moving)
            if chance is not None and (worst is None or chance > worst):
                worst = chance
        return {"kind": "move", "break_worst": worst or 0, "enemy_can_fire": worst is not None, "of": self.odds.ONE}

    def for_command(self, lc: LegalCommand) -> dict[str, Any] | None:
        command = lc.command
        action = command.action
        fg = self.state.fire_group
        if action in ("group_add", "group_add_weapon") and command.hex is not None and command.units:
            member = (command.units[0], command.weapon)
            if fg is not None and fg.target == command.hex:
                return self._shot(FireGroup(command.hex, fg.members + (member,), fg.leader))
            return self._shot(FireGroup(command.hex, (member,), None))
        if action == "group_leader" and fg is not None and command.units:
            return self._shot(FireGroup(fg.target, fg.members, command.units[0]))
        if action == "group_fire" and fg is not None:
            return self._shot(fg)
        if action in ("move", "stack_move"):
            return self._move(lc, moving=True)
        if action in ("advance", "rout"):
            return self._move(lc, moving=False)
        if action == "cc_attack":
            return self._close_combat(lc)
        if action == "rally" and command.units:
            return self._rally(self.state.units[command.units[0]])
        if action == "stay" and command.units:
            unit = self.state.units[command.units[0]]
            if unit.hex is None:
                return None
            chance = self.view.loss(unit, unit.hex, False)
            return {"kind": "stay", "break": chance or 0, "enemy_can_fire": chance is not None, "of": self.odds.ONE}
        return None

    def _close_combat(self, lc: LegalCommand) -> dict[str, Any] | None:
        extra = dict(lc.command.extra)
        attackers = tuple(lc.command.units)
        targets = tuple(int(t) for t in extra.get("targets", ()) or ())
        if not attackers or not targets:
            return None
        if any(not visible_to(self.state, self.state.units[t], self.view.viewer) for t in targets):
            return None
        leader = extra.get("leader")
        ways = self.odds.WAYS
        ours = self.view._kill_ways(attackers, targets, None if leader is None else int(leader))
        unbroken = tuple(t for t in targets if not self.state.units[t].broken)
        theirs = self.view._kill_ways(unbroken, attackers, self.view._best_leader(unbroken)) if unbroken else 0
        return {"kind": "close_combat", "kill": ours * ways, "killed": theirs * ways, "of": self.odds.ONE}

    def _rally(self, unit: Unit) -> dict[str, Any]:
        return {"kind": "rally", "rally": self._rally_ways(unit) * self.odds.WAYS, "of": self.odds.ONE}

    def _rally_ways(self, unit: Unit) -> int:
        """The same sum as `OddsView._rally_text`: rule 14.2 with rule 14.6, less the roll
        that removes the unit."""
        from slcore.rules import r14_rally, r15_leadership, r26_fanaticism
        from slcore.rules.r12_morale import morale_value

        types = self.engine.types
        modifier, _ = r15_leadership.modifier_for_check(self.state, types, unit)
        modifier += r26_fanaticism.modifier_for(self.state, unit)
        target = morale_value(types, unit) - (r14_rally.DESPERATION_PENALTY if unit.dm else 0)
        return sum(
            count
            for roll, count in self.odds.DICE_WAYS.items()
            if roll + modifier <= target and roll != r14_rally.SELF_CASUALTY_ROLL
        )


def odds_text(odds: Mapping[str, Any]) -> str:
    """The odds in words, for a label or a tooltip."""
    whole = int(odds.get("of", 1296)) or 1296

    def pct(value: Any) -> str:
        return f"{(int(value) * 100 + whole // 2) // whole}%"

    kind = odds.get("kind")
    if kind == "fire":
        return f"result {pct(odds['result'])}, kill {pct(odds['kia'])}, break {pct(odds['break'])}"
    if kind == "move":
        return f"break {pct(odds['break_worst'])}" if odds.get("enemy_can_fire") else "no visible enemy can fire"
    if kind == "stay":
        return f"break here {pct(odds['break'])}" if odds.get("enemy_can_fire") else "no visible enemy can fire"
    if kind == "close_combat":
        return f"kill {pct(odds['kill'])}, killed {pct(odds['killed'])}"
    if kind == "rally":
        return f"rally {pct(odds['rally'])}"
    return ""


def legal_entries(
    engine: Engine,
    state: State,
    frame: DecisionFrame,
    names: Names,
    viewer: int,
    with_odds: bool,
) -> list[dict[str, Any]]:
    """The legal list of a frame as the protocol sends it (version 2)."""
    calculator = FrameOdds(engine, state, viewer) if with_odds and frame.commands else None
    blind = blind_hexes(engine, state, frame.player) if frame.commands else frozenset()
    out: list[dict[str, Any]] = []
    for lc in frame.commands:
        entry: dict[str, Any] = {
            "id": lc.id,
            "action": lc.command.action,
            "payload": lc.payload,
            "label": command_label(state, lc, names, viewer, blind),
            "units": [{"id": uid, "name": names.for_viewer(state, uid, viewer)} for uid in lc.command.units],
            "hexes": command_hexes(state, lc, viewer),
        }
        if calculator is not None:
            found = calculator.for_command(lc)
            if found is not None:
                entry["odds"] = found
        out.append(entry)
    return out


# ------------------------------------------------------------------ game over


def casualties(state: State) -> dict[str, dict[str, int]]:
    """The losses of each side at the end: squads, leaders, and vehicles."""
    out: dict[str, dict[str, int]] = {"0": {"squads": 0, "leaders": 0, "vehicles": 0}, "1": {"squads": 0, "leaders": 0, "vehicles": 0}}
    for unit in state.units:
        side = out.get(str(unit.player))
        if side is None:
            continue
        if unit.is_vehicle:
            if unit.eliminated or unit.wreck:
                side["vehicles"] += 1
        elif unit.kind == KIND_LEADER:
            if unit.eliminated:
                side["leaders"] += 1
        elif unit.is_infantry and unit.eliminated:
            side["squads"] += 1
    return out


def game_end_conditions(log: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The conditions of the `game_end` line of the log, the newest one."""
    for entry in reversed(list(log)):
        if entry.get("kind") == "game_end":
            conditions = (entry.get("data") or {}).get("conditions")
            return list(conditions) if isinstance(conditions, list) else []
    return []
