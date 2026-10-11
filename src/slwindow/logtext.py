"""The text of one action log entry in the two desktop windows (FR-06).

Each entry shows the rule ID, what occurred, the hex, the units, the result, the dice, and
each modifier with its cause, as the browser log does (`client/src/log/panel.ts`). The host
names the units and the sides in protocol version 2. For a version 1 entry the unit is
its id, and the name from the view of the window where it has one.

`EVENT_TEXT` gives each kind of entry a short text in the project's own words, and the
same table is in the browser log. `tests/host/test_annotate_coverage.py` holds the table to
each event kind the core emits, and it holds the two clients to the same text for the same
entry. There is no rulebook text here.

The text comes from the fields of the entry and nothing else. It applies no rule (AR-06).
"""

from __future__ import annotations

from typing import Any

# What occurred, for each kind of log entry: the events of the core and the notes of the
# host. The text is short, because the fields of the entry follow it.
EVENT_TEXT: dict[str, str] = {
    # The turn, the phases, and the set up (rules 4 and 21).
    "turn_start": "a new turn starts",
    "phase": "a new phase starts",
    "player_turn_end": "the player turn ends",
    "first_mover": "the roll for the side that moves first",
    "place": "place a unit",
    "place_weapon": "a weapon is given to a unit",
    "setup_done": "a side completed its set up",
    "hidden": "a unit is placed hidden",
    "game_end": "the game ends",
    # Movement (rules 5, 6, and 13).
    "move": "a unit moves",
    "stack_move": "a stack moves together",
    "advance": "a unit advances",
    "pickup": "a unit picks up a weapon",
    "drop": "a unit drops a weapon",
    "captured": "a unit captures a weapon of the other side and keeps it",
    "captured_eliminated": "a unit captures a weapon of the other side, and the weapon is removed",
    "abandon_weapon": "a unit leaves a weapon in the hex",
    "stopped": "a unit is stopped by a hidden enemy unit and stays short of the hex",
    "revealed": "a hidden unit is shown on the board",
    # Fire (rules 8 to 11, 16, 17, and 24).
    "group_add": "a unit joins the fire group",
    "group_leader": "a leader directs the fire group",
    "fire": "the fire group fires",
    "fire_result": "the result of the fire on the hex",
    "smoke_modifier": "smoke between the firer and the target",
    "penetration": "a machine gun fires through to the next hex",
    "malfunction": "a weapon breaks down",
    "weapon_eliminated": "a weapon in the hex is destroyed",
    "track_return": "the defender puts moving units back on their track",
    "track_return_end": "a unit that went back returns to the hex where it stopped",
    # Morale, rout, and rally (rules 12 to 15 and 18).
    "morale_pass": "a unit passes its morale check",
    "broken": "a unit is broken",
    "eliminated": "a unit is eliminated",
    "berserk": "a unit goes berserk",
    "berserk_join": "a unit joins the berserk charge of its leader",
    "berserk_join_failed": "a unit does not join the berserk charge of its leader",
    "rout": "a broken unit routs",
    "stay": "a broken unit stays in cover",
    "rallied": "a broken unit rallies",
    "rally_failed": "a broken unit fails to rally",
    "repaired": "a broken weapon is repaired",
    "repair_failed": "the repair of a weapon fails",
    "weapon_removed": "a broken weapon is removed",
    # Close combat (rule 20).
    "cc_declare": "units declare a close combat attack",
    "cc_kill": "a close combat attack kills its targets",
    "cc_miss": "a close combat attack has no effect",
    "cc_no_attack": "a close combat attack has no firepower and does not roll",
    "melee": "the units in the hex stay locked in melee",
    # Flamethrowers, demolition charges, smoke, concealment, and sewers (rules 22 to 27).
    "out_of_fuel": "a flamethrower runs out of fuel",
    "demo_placed": "a unit places a demolition charge",
    "demo_armed": "a demolition charge is ready to explode",
    "demo_dud": "a demolition charge does not arm and stays with its unit",
    "demo_explode": "a demolition charge explodes",
    "sewer_closed": "the explosion closes the sewer entrance",
    "smoke": "a unit makes smoke",
    "smoke_gone": "the smoke clears",
    "concealed": "a concealment counter goes on the hex",
    "unconcealed": "a concealment counter is removed",
    "sewer_move": "units go through the sewer",
    "sewer_lost": "units are lost in the sewer",
    "sewer_surface": "units lost in the sewer come up",
    "left_behind": "a weapon too heavy for the sewer stays behind",
    # Vehicles and the armour rules (rules 28 to 41 and 63).
    "vehicle_move": "a vehicle moves",
    "vehicle_pivot": "a vehicle turns in its hex",
    "breakdown_roll": "the roll for a mechanical breakdown of a vehicle",
    "board": "a unit gets on a vehicle",
    "debark": "a unit gets off a vehicle",
    "debark_cost": "the vehicle pays for the unit that got off",
    "dismount": "a passenger gets off",
    "passenger_eliminated": "a passenger is eliminated with its vehicle",
    "to_hit": "a gun fires at a target",
    "kill_roll": "the roll to kill a vehicle that was hit",
    "heat_spent": "a gun uses its last HEAT round",
    "gun_malfunction": "the main gun of a vehicle breaks down",
    "afv_fire": "a vehicle fires high explosive at infantry",
    "afv_mg_fire": "a vehicle fires its machine guns",
    "mg_malfunction": "the machine guns of a vehicle break down",
    "canister_spent": "a gun uses its last canister round",
    "crew_exposed": "the crew of a vehicle opens its hatches",
    "crew_inside": "the crew of a vehicle closes its hatches",
    "crew_fire": "infantry fire hits the exposed crew of a vehicle",
    "crew_survival": "the roll for the crew of a destroyed vehicle",
    "crew_morale": "the morale check of the crew of a vehicle",
    "crew_abandons": "the crew abandons its vehicle",
    "immobilized": "a vehicle is immobilized",
    "wreck": "a vehicle is destroyed and leaves a wreck",
    "wreck_pushed": "a vehicle pushes a wreck out of its way",
    "overrun": "a vehicle overruns the infantry of a hex",
    "overrun_unarmed": "a vehicle with no weapon drives through the infantry of a hex",
<<<<<<< Updated upstream
=======
    # PR-54: the overrun is declared on entry and resolves after the Defensive Fire Phase.
    "overrun_declared": "a vehicle drives into the infantry of a hex and will overrun it after the defensive fire",
    "overrun_stopped": "the defensive fire stopped the vehicle, and it makes no overrun",
    "overrun_empty": "no enemy infantry is left in the hex, so the vehicle makes no overrun",
>>>>>>> Stashed changes
    "grenade_bundle": "a grenade bundle immobilizes the overrunning vehicle",
    "pushed_out": "a unit steps out from below an enemy vehicle",
    "crushed": "a unit that cannot step out from below a vehicle is crushed",
    "pre_afv_check": "the morale check before an attack on a vehicle",
    "immobilize_attempt": "infantry tries to immobilize a vehicle",
    "close_combat_vs_afv": "infantry attacks a vehicle in close combat",
    "returned": "a unit goes back to the hex it came from",
    "passenger_fire": "the passengers of a vehicle are fired at",
    "at_to_hit": "an anti-tank weapon fires at a vehicle",
    "bazooka_spent": "a bazooka is out of rounds",
    "panzerfaust_used": "a panzerfaust is used and removed",
    "flamethrower_hit": "a flamethrower hits a vehicle",
    "flamethrower_infantry": "the flamethrower also hits the infantry of the hex",
    "afv_repaired": "a vehicle repairs a broken weapon",
    "afv_repair_failed": "the repair of a vehicle weapon fails",
    "afv_disabled": "a vehicle weapon is out of action for the game",
    "afv_smoke": "a vehicle fires a smoke round",
    "smoke_dischargers": "a vehicle fires its smoke dischargers",
    # The notes of the host, which are not rules of the game.
    "forced_command": "the host applied the only legal command",
    "undo": "a side took back commands",
    "setup_helper": "the set up helper placed a side",
}

# The fields that name one unit, and the fields that name a list of units.
UNIT_FIELDS = ("unit", "leader", "vehicle", "carrier", "crew", "attacker", "target_unit")
UNIT_LIST_FIELDS = ("units", "attackers", "targets", "wrecks")
# The fields that hold a player index.
SIDE_FIELDS = ("player", "phasing", "winner", "firer", "from_player", "next_phasing")
# The kinds where `target` is the unit that was hit, and not a number the dice must reach.
TARGET_UNIT_KINDS = ("kill_roll",)
# The fields the text does not show. The event kind already says what they would say, or
# they are the data of a replay and not of a person.
SILENT_FIELDS = ("phase", "conditions", "counter", "concealed", "text", "names", "sides")

DIRECTION_TEXT = ("north", "north-east", "south-east", "south", "south-west", "north-west")
AMMO_TEXT = {"ap": "armour-piercing", "he": "high explosive", "heat": "HEAT", "canister": "canister"}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _signed(value: int) -> str:
    return f"{'+' if value >= 0 else ''}{value}"


def _halves(value: int) -> str:
    return f"{value // 2}.5" if value % 2 else f"{value // 2}"


def direction_text(value: Any) -> str:
    """A facing or a direction index as a compass word: 1 gives "north-east"."""
    if _is_int(value) and 0 <= value < len(DIRECTION_TEXT):
        return DIRECTION_TEXT[value]
    return str(value)


def _unit_text(value: Any, names: dict[int, str]) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or f"#{value.get('id')}")
    if isinstance(value, str):
        return value
    try:
        unit_id = int(value)
    except (TypeError, ValueError):
        return str(value)
    name = names.get(unit_id)
    return name if name else f"#{unit_id}"


def _names_of(view: dict[str, Any] | None) -> dict[int, str]:
    out: dict[int, str] = {}
    if not isinstance(view, dict):
        return out
    for unit in view.get("units", []) or []:
        if isinstance(unit, dict) and unit.get("id") is not None and unit.get("name"):
            out[int(unit["id"])] = f"{unit['name']} [{unit['id']}]"
    return out


def _modifier_text(modifier: Any) -> str:
    if isinstance(modifier, str):
        return modifier
    if isinstance(modifier, dict):
        value = modifier.get("value", 0)
        try:
            sign = "+" if int(value) >= 0 else ""
        except (TypeError, ValueError):
            sign = ""
        cause = modifier.get("cause", "")
        rule = modifier.get("rule", "")
        text = f"{sign}{value} {cause}".strip()
        return f"{text} ({rule})" if rule else text
    return str(modifier)


def _entry_names(entry: dict[str, Any], view: dict[str, Any] | None) -> dict[int, str]:
    """The unit names of one entry: the `names` of the host (version 2) first, then the
    names of the view."""
    names = _names_of(view)
    given = entry.get("names")
    if isinstance(given, dict):
        for key, value in given.items():
            try:
                names[int(key)] = str(value)
            except (TypeError, ValueError):
                continue
    return names


def _side_text(entry: dict[str, Any], player: Any) -> str:
    sides = entry.get("sides")
    if isinstance(sides, dict) and str(player) in sides:
        return str(sides[str(player)])
    return f"player {player}"


def _flag(data: dict[str, Any], key: str, yes: str, no: str) -> str | None:
    value = data.get(key)
    if isinstance(value, bool):
        return yes if value else no
    return None


def describe(entry: dict[str, Any], view: dict[str, Any] | None = None, tabletop: bool = False) -> str:
    """One line for one log entry, without the rule ID (the panel draws it first).

    `tabletop` hides the dice and the modifiers and keeps the rule ID and the result, the
    same switch as the browser log. `describe` in `client/src/log/panel.ts` gives the same
    text for the same entry.
    """
    data = entry.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    names = _entry_names(entry, view)
    kind = str(entry.get("kind", ""))
    text = entry.get("text")
    title = text if isinstance(text, str) and text else EVENT_TEXT.get(kind, kind.replace("_", " "))
    parts: list[str] = [title]
    target_is_unit = kind in TARGET_UNIT_KINDS and _is_int(data.get("target"))
    # The hexes.
    where = next((data[k] for k in ("target", "hex", "to") if isinstance(data.get(k), str)), None)
    if where is not None:
        parts.append(f"at {where}")
    if isinstance(data.get("from"), str) and data.get("to") is not None:
        parts.append(f"from {data['from']}")
    if isinstance(data.get("goal"), str):
        parts.append(f"towards {data['goal']}")
    if isinstance(data.get("tried"), str):
        parts.append(f"short of {data['tried']}")
    if isinstance(data.get("left_in"), str):
        parts.append(f"left in {data['left_in']}")
    # The units.
    for key in UNIT_FIELDS:
        value = data.get(f"{key}_name", data.get(key))
        if value is not None and not isinstance(value, bool):
            parts.append(f"{key.replace('_', ' ')} {_unit_text(value, names)}")
    if target_is_unit:
        parts.append(f"target {_unit_text(data['target'], names)}")
    for key in UNIT_LIST_FIELDS:
        values = data.get(f"{key}_names", data.get(key))
        if isinstance(values, list) and values:
            parts.append(f"{key} {', '.join(_unit_text(v, names) for v in values)}")
    members = data.get("members")
    if isinstance(members, list) and members:
        firers = [_unit_text(m.get("unit"), names) for m in members if isinstance(m, dict) and m.get("unit") is not None]
        if firers:
            parts.append(f"firers {', '.join(firers)}")
    if data.get("weapon") is not None:
        parts.append(f"weapon {_unit_text(data.get('weapon_name', data['weapon']), names)}")
    if _is_int(data.get("charge")):
        parts.append(f"charge {_unit_text(data['charge'], names)}")
    side = data.get("side_name", data.get("side"))
    if isinstance(side, str) and side:
        parts.append(f"side {side}")
    for key in SIDE_FIELDS:
        value = data.get(key)
        if _is_int(value):
            parts.append(f"{key.replace('_', ' ')} {_side_text(entry, value)}")
    for key in ("turn", "next_turn"):
        if _is_int(data.get(key)):
            parts.append(f"{key.replace('_', ' ')} {data[key]}")
    # What the rule gave.
    if isinstance(data.get("result"), str):
        parts.append(f"result {data['result']}")
    if _is_int(data.get("firepower")):
        parts.append(f"{data['firepower']} firepower")
    if _is_int(data.get("attack")) and _is_int(data.get("defense")):
        parts.append(f"attack {data['attack']} against defence {data['defense']}")
    if isinstance(data.get("odds"), str):
        parts.append(f"odds {data['odds']}, kill on {data.get('kill')}")
    if _is_int(data.get("facing")):
        parts.append(f"facing {direction_text(data['facing'])}")
    if _is_int(data.get("was")):
        parts.append(f"was facing {direction_text(data['was'])}")
    if isinstance(data.get("aim"), str):
        parts.append(f"aimed at {data['aim']}")
    if isinstance(data.get("ammo"), str):
        parts.append(f"{AMMO_TEXT.get(data['ammo'], data['ammo'])} round")
    if isinstance(data.get("face"), str):
        parts.append(f"on the {data['face'].replace('_', ' ')}")
    if isinstance(data.get("location"), str):
        parts.append(f"at the {data['location'].replace('_', ' ')}")
    if isinstance(data.get("row"), str):
        parts.append(f"row {data['row'].replace('_', ' ')}")
    if _is_int(data.get("range")):
        parts.append(f"range {data['range']}")
    for flag in (
        _flag(data, "hit", "hit", "miss"),
        _flag(data, "killed", "killed", "not killed"),
        _flag(data, "survived", "the crew survives", "the crew is lost"),
        _flag(data, "stayed", "the crew stays", "the crew leaves"),
        _flag(data, "passed", "passed", "failed"),
        _flag(data, "reached", "reached its goal", "did not reach its goal"),
    ):
        if flag is not None:
            parts.append(flag)
    for key, text in (
        ("immobilized", "immobilized"),
        ("hull_down", "hull down"),
        ("after_movement", "after its movement"),
        ("desperation", "desperation"),
    ):
        if data.get(key) is True:
            parts.append(text)
    if _is_int(data.get("left")):
        parts.append(f"{data['left']} left")
    if _is_int(data.get("factor")):
        parts.append(f"{data['factor']} of {data.get('of')} firepower goes on")
    if not tabletop:
        dice = data.get("dice")
        if isinstance(dice, list) and dice:
            parts.append(f"dice {' and '.join(str(d) for d in dice)}")
        if _is_int(data.get("die")):
            parts.append(f"die {data['die']}")
        for key in ("roll", "raw"):
            if _is_int(data.get(key)):
                parts.append(f"roll {data[key]}")
        if _is_int(data.get("third_die")):
            parts.append(f"third die {data['third_die']}")
        if _is_int(data.get("column")):
            parts.append(f"column {data['column']}")
        elif isinstance(data.get("column"), str):
            parts.append(f"column {data['column'].replace('_', ' ')}")
        cases = data.get("cases")
        if isinstance(cases, list) and cases:
            parts.append(f"cases {', '.join(str(c) for c in cases)}")
        if _is_int(data.get("adjusted")):
            parts.append(f"adjusted {data['adjusted']}")
        modifier = data.get("modifier")
        if _is_int(modifier):
            parts.append(f"modifier {_signed(modifier)}")
        if _is_int(data.get("value")):
            parts.append(f"modifier {_signed(data['value'])}")
        if _is_int(data.get("armor_modifier")) and data["armor_modifier"] != 0:
            parts.append(f"armour modifier {_signed(data['armor_modifier'])}")
        modifiers = data.get("modifiers")
        if isinstance(modifiers, list) and modifiers:
            parts.append(f"modifiers {', '.join(_modifier_text(m) for m in modifiers)}")
        leadership = data.get("leadership")
        if _is_int(leadership) and leadership != 0:
            parts.append(f"leader {_signed(leadership)}")
        fanatic = data.get("fanatic")
        if _is_int(fanatic) and fanatic != 0:
            parts.append(f"fanatic {_signed(fanatic)}")
        if _is_int(data.get("morale")):
            parts.append(f"morale {data['morale']}")
        target = data.get("target")
        if _is_int(target) and not target_is_unit:
            # A rally names the number the dice must reach, not a unit.
            parts.append(f"needs {target}")
        for key, text in (("needed", "needs"), ("survival", "survives on"), ("breaks_on", "breaks down on"), ("breakdown", "breaks down on")):
            if _is_int(data.get(key)):
                parts.append(f"{text} {data[key]}")
        if _is_int(data.get("cost_halves")):
            parts.append(f"{_halves(int(data['cost_halves']))} movement factors")
        if _is_int(data.get("halves")):
            parts.append(f"{_halves(int(data['halves']))} movement factors")
        rules = data.get("rules")
        if isinstance(rules, list) and rules:
            parts.append(f"rules {', '.join(str(r) for r in rules)}")
    if isinstance(data.get("label"), str):
        # A command the host applied for a person, because the frame had one.
        parts.append(str(data["label"]))
    if _is_int(data.get("commands")):
        parts.append(f"{data['commands']} commands")
    if isinstance(data.get("cause"), str):
        parts.append(str(data["cause"]))
    return ", ".join(parts)


# Each data field that `describe` reads. The coverage test holds each field the core
# writes to this list or to SILENT_FIELDS, so a new field is not dropped in silence.
SHOWN_FIELDS = (
    "target", "hex", "to", "from", "goal", "tried", "left_in",
    *UNIT_FIELDS, *UNIT_LIST_FIELDS, "members", "weapon", "charge", "side", *SIDE_FIELDS,
    "turn", "next_turn", "result", "firepower", "attack", "defense", "odds", "kill", "facing", "was", "aim", "ammo",
    "face", "location", "row", "range", "hit", "killed", "survived", "stayed", "passed",
    "reached", "immobilized", "hull_down", "after_movement", "desperation", "left", "factor",
    "of", "dice", "die", "roll", "raw", "third_die", "column", "cases", "adjusted", "modifier",
    "value", "armor_modifier", "modifiers", "leadership", "fanatic", "morale", "needed",
    "survival", "breaks_on", "breakdown", "cost_halves", "halves", "rules", "label",
    "commands", "cause",
)


def line(entry: dict[str, Any], view: dict[str, Any] | None = None, tabletop: bool = False) -> str:
    """The rule ID and the text of one entry, as one line."""
    rule = entry.get("rule_id", "")
    body = describe(entry, view, tabletop)
    return f"{rule} {body}".strip()
