"""Each action and each event of the core has its own text in each client (FR-06).

The core grows new actions and new events with each rule. A client that has no text for
one shows the raw name, or a label that says nothing of the facing, the round, or the
hex. These tests read the core itself, so a new action, a new event kind, a new data
field, a new window sub-step, or a new rule number fails here until the host and the
clients describe it:

- `slhost.annotate.command_label` for each action of `slcore.actions.ACTION_SPECS`
- `slhost.annotate.STEP_TEXT` for each window sub-step of `slcore.phases.PHASE_STEPS`
- `slwindow.logtext.EVENT_TEXT` for each event kind the core and the host emit, and the
  same table in `client/src/log/panel.ts`
- a topic in `client/src/log/rules.ts` for each rule number the core names

The last test builds the browser log with the esbuild of the client and runs it in node on
the log of real games, and the text of each line must be the text of the desktop log.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from slcli.play import build_engine, make_agent, play_game
from slcore import geometry
from slcore.actions import ACTION_SPECS
from slcore.commands import ACTIONS, Command
from slcore.frame import LegalCommand
from slcore.phases import PHASE_STEPS, WINDOW
from slhost import annotate
from slwindow import logtext

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "src" / "slcore"
SERVER = ROOT / "src" / "slhost" / "server.py"
PANEL = ROOT / "client" / "src" / "log" / "panel.ts"
RULES = ROOT / "client" / "src" / "log" / "rules.ts"
ESBUILD = ROOT / "client" / "node_modules" / ".bin" / "esbuild"


# ------------------------------------------------------------ what the core emits


def _strings(node: ast.AST | None) -> list[str]:
    """The text constants an expression can give: a constant, or each branch of an `if`."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.IfExp):
        return _strings(node.body) + _strings(node.orelse)
    return []


def _event_calls() -> list[tuple[Path, ast.Call]]:
    out = []
    for path in sorted(CORE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Event":
                out.append((path, node))
    return out


def core_event_kinds() -> dict[str, str]:
    """Each event kind the core emits, with the first place that emits it."""
    kinds: dict[str, str] = {}
    unread = []
    for path, call in _event_calls():
        arg = call.args[1] if len(call.args) > 1 else next((k.value for k in call.keywords if k.arg == "kind"), None)
        found = _strings(arg)
        if not found:
            unread.append(f"{path.name}:{call.lineno}")
        for kind in found:
            kinds.setdefault(kind, f"{path.name}:{call.lineno}")
    assert not unread, f"an event kind that is not a text constant cannot be checked: {unread}"
    return kinds


def host_event_kinds() -> set[str]:
    return set(re.findall(r'"kind": "([a-z_]+)"', SERVER.read_text(encoding="utf-8")))


def core_data_fields() -> dict[str, str]:
    """Each data key the core writes into an event: the keys of the dictionaries that go
    in an `Event`, or into a variable named `data`."""
    fields: dict[str, str] = {}
    for path in sorted(CORE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            found: ast.Dict | None = None
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Event" and len(node.args) > 2:
                if isinstance(node.args[2], ast.Dict):
                    found = node.args[2]
            elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
                if any(getattr(t, "id", "") == "data" for t in node.targets):
                    found = node.value
            elif (
                isinstance(node, ast.Subscript)
                and isinstance(node.ctx, ast.Store)
                and getattr(node.value, "id", "") == "data"
                and isinstance(node.slice, ast.Constant)
            ):
                fields.setdefault(str(node.slice.value), f"{path.name}:{node.lineno}")
            if found is not None:
                for key in found.keys:
                    if isinstance(key, ast.Constant):
                        fields.setdefault(str(key.value), f"{path.name}:{node.lineno}")
    return fields


def core_rule_ids() -> set[str]:
    """Each rule ID the core names: the `RULE_` constants and the first text of an `Event`."""
    ids: set[str] = set()
    for path in sorted(CORE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                if any(getattr(t, "id", "").startswith("RULE_") for t in node.targets):
                    ids.add(node.value.value)
    for _, call in _event_calls():
        if call.args:
            ids.update(_strings(call.args[0]))
    return ids


# ------------------------------------------------------------------ the labels


@pytest.fixture(scope="module")
def armor():
    engine = build_engine("s04_armor_probe")
    return engine, engine.new_game(1)


def _command(action: str) -> Command:
    """A command of this action with the fields its label reads. Unit 0 and unit 1 are
    real units of the scenario, so the label names them."""
    extras: dict[str, tuple] = {
        "place": (("facing", 1),),
        "vehicle_move": (("facing", 1),),
        "vehicle_pivot": (("facing", 2),),
        "afv_fire": (("aim", "vehicle"), ("ammo", "heat")),
        "afv_repair": (("armament", "main"),),
        "board": (("vehicle", 1),),
        "cc_attack": (("targets", (1,)),),
        "explode_demo": (("charge", 1),),
    }
    no_units = {"end_phase", "end_setup", "group_fire", "place_concealment", "sewer_return", "explode_demo", "repair"}
    weapons = {"place_weapon", "pickup", "drop", "repair", "group_add_weapon", "ft_fire", "place_demo", "at_fire"}
    return Command(
        action,
        units=() if action in no_units else (0,),
        hex=(3, 4),
        weapon=1 if action in weapons else None,
        extra=extras.get(action, ()),
    )


def test_the_action_table_of_the_core_is_the_command_list():
    assert set(ACTION_SPECS) == set(ACTIONS)


@pytest.mark.parametrize("action", sorted(ACTION_SPECS))
def test_each_action_of_the_core_has_its_own_label(armor, action: str):
    _, state = armor
    command = _command(action)
    label = annotate.command_label(state, LegalCommand(command.id, command), annotate.Names(), 0)
    names = annotate.Names()
    who = " and ".join(names.for_viewer(state, uid, 0) for uid in command.units)
    assert label != annotate.fallback_label(action, who, geometry.hex_id(*command.hex)), (
        f"annotate.command_label has no text of its own for {action!r}"
    )
    assert "_" not in label, f"the label of {action} shows a raw name: {label!r}"


def label_for(state, command: Command, blind: frozenset = frozenset()) -> str:
    return annotate.command_label(state, LegalCommand(command.id, command), annotate.Names(), 0, blind)


def test_the_new_labels_say_the_facing_the_round_and_the_step(armor):
    _, state = armor
    move = label_for(state, Command("vehicle_move", units=(0,), hex=(3, 4), extra=(("facing", 1),)))
    assert " to D4, facing north-east" in move
    assert "face south-east" in label_for(state, Command("vehicle_pivot", units=(0,), extra=(("facing", 2),)))
    heat = label_for(state, Command("afv_fire", units=(0,), hex=(3, 4), extra=(("aim", "vehicle"), ("ammo", "heat"))))
    assert "HEAT round" in heat and "vehicle" in heat
    armour = label_for(state, Command("afv_fire", units=(0,), hex=(3, 4), extra=(("aim", "vehicle"), ("ammo", "ap"))))
    assert "armour-piercing round" in armour
    push = label_for(state, Command("push_out", units=(0,), hex=(3, 4)))
    assert "steps out from below the enemy vehicle to D4" in push
    repair = label_for(state, Command("afv_repair", units=(0,), extra=(("armament", "mg"),)))
    assert repair.startswith("repair the machine guns of ")


def test_a_shot_into_a_blind_hex_says_blind(armor):
    """Rule 42.4 and PR-52: the label of a shot at a hex with no known enemy."""
    _, state = armor
    shot = Command("group_add", units=(0,), hex=(3, 4))
    assert "fires blind into D4" in label_for(state, shot, frozenset({(3, 4)}))
    assert "fires at D4" in label_for(state, shot)
    gun = Command("afv_fire", units=(0,), hex=(3, 4), extra=(("aim", "infantry"), ("ammo", "he")))
    assert "blind into D4" in label_for(state, gun, frozenset({(3, 4)}))


def test_the_host_offers_the_blind_shots_of_a_real_frame():
    """The legal list of a side that faces hidden units names its blind shots."""
    from slcore.rules import r42_hidden

    engine = build_engine("s00c_two_board_advance")
    attacker = engine.scenario.side_index("attacker")
    board = engine.board
    spot = hide = None
    for h in board:
        if r42_hidden.hex_allows_hiding(board, h.ref):
            spot = next((n for n in board.neighbors(h.ref) if board.hex(n).terrain == "open"), None)
            if spot is not None:
                hide = h.ref
                break
    assert spot is not None and hide is not None
    state = engine.new_game(5)
    squad = next(u for u in state.units if u.kind == "squad" and u.player == attacker)
    units = [
        u.with_(hex=spot) if u.id == squad.id else u.with_(hex=None, eliminated=u.kind != "sw")
        for u in state.units
    ]
    index = next(i for i, s in enumerate(PHASE_STEPS["prep_fire"]) if s.name == "fire_window")
    state = state.with_(
        units=tuple(units),
        phase="prep_fire",
        sub_step=index,
        phasing=attacker,
        active=attacker,
        setup_index=len(engine.scenario.setup_order),
    )
    frame = engine.legal_commands(state)
    entries = annotate.legal_entries(engine, state, frame, annotate.Names(), attacker, False)
    blind = [e["label"] for e in entries if e["payload"].get("hex") == geometry.hex_id(*hide) and e["action"] == "group_add"]
    assert blind and all("blind into" in label for label in blind), blind


# -------------------------------------------------------------- the phase strip


def test_each_window_sub_step_has_a_text():
    missing = [
        f"{phase}/{step.name}"
        for phase, steps in PHASE_STEPS.items()
        for step in steps
        if step.kind == WINDOW and f"{phase}/{step.name}" not in annotate.STEP_TEXT
    ]
    assert not missing, f"annotate.STEP_TEXT has no text for {missing}"
    assert "adjacent hex" in annotate.phase_text("defensive_fire", "push_out")
    assert annotate.phase_text("defensive_fire", "fire_window") == annotate.PHASE_TEXT["defensive_fire"]
    assert annotate.phase_text("close_combat", "game_over") == annotate.PHASE_TEXT["game_over"]


# ------------------------------------------------------------------ the log text


def test_each_event_kind_of_the_core_and_the_host_has_a_log_text():
    kinds = core_event_kinds()
    assert len(kinds) > 100, "the scan of the core found too few events to be a scan"
    missing = sorted(f"{kind} ({where})" for kind, where in kinds.items() if kind not in logtext.EVENT_TEXT)
    assert not missing, f"slwindow.logtext.EVENT_TEXT has no text for {missing}"
    host = host_event_kinds()
    assert {"forced_command", "undo", "setup_helper"} <= host
    assert not host - set(logtext.EVENT_TEXT)


def test_each_data_field_of_the_core_is_shown_or_named_as_silent():
    fields = core_data_fields()
    known = set(logtext.SHOWN_FIELDS) | set(logtext.SILENT_FIELDS)
    missing = sorted(f"{key} ({where})" for key, where in fields.items() if key not in known)
    assert not missing, f"slwindow.logtext does not show {missing}, and does not name them as silent"


def ts_table(text: str, name: str) -> dict[str, str]:
    match = re.search(rf"export const {name}: Record<string, string> = \{{(.*?)\n\}};", text, re.S)
    assert match, f"{name} is not in the client source"
    return dict(re.findall(r'^\s*([a-z_]+): "([^"]*)",$', match.group(1), re.M))


def test_the_browser_log_has_the_same_event_table():
    assert ts_table(PANEL.read_text(encoding="utf-8"), "EVENT_TEXT") == logtext.EVENT_TEXT


def test_the_host_and_the_logs_use_the_same_compass_words():
    assert annotate.FACING_TEXT == logtext.DIRECTION_TEXT
    panel = PANEL.read_text(encoding="utf-8")
    words = re.search(r"const DIRECTION_TEXT = \[(.*?)\];", panel)
    assert words and tuple(re.findall(r'"([^"]+)"', words.group(1))) == logtext.DIRECTION_TEXT


def test_each_rule_number_of_the_core_has_a_tooltip_topic():
    text = RULES.read_text(encoding="utf-8")
    table = re.search(r"const TOPICS: Record<string, string> = \{(.*?)\n\};", text, re.S)
    assert table
    topics = set(re.findall(r'^\s*"(\d+)":', table.group(1), re.M))
    numbers = {m.group(1) for rule in core_rule_ids() if (m := re.match(r"^(\d+)", rule))}
    assert "63" in numbers, "the scan did not find the HEAT rule, so it is not a scan"
    assert not numbers - topics, f"client/src/log/rules.ts has no topic for rules {sorted(numbers - topics)}"
    assert "PR-" in text, "a project ruling ID has a topic too"


def test_the_log_names_the_vehicle_of_a_kill_roll_and_the_crew(armor):
    """A kill roll holds the vehicle in `target`, and a crew line holds the crew counter."""
    engine, state = armor
    entry = {"rule_id": "33.4", "kind": "kill_roll", "data": {"unit": 0, "target": 1, "raw": 4, "adjusted": 4, "needed": 8, "killed": True}}
    dressed = annotate.dress_line(entry, state, annotate.Names(), -1, annotate.side_names(engine))
    assert "1" in dressed["names"] and "0" in dressed["names"]
    text = logtext.line(dressed)
    assert f"target {dressed['names']['1']}" in text and "needs 8" in text and "killed" in text
    assert "needs 1," not in text, "the target of a kill roll is a unit, not a number the dice must reach"
    crew = {"rule_id": "33.9", "kind": "crew_abandons", "data": {"vehicle": 0, "crew": 1}}
    dressed = annotate.dress_line(crew, state, annotate.Names(), -1, annotate.side_names(engine))
    assert f"crew {dressed['names']['1']}" in logtext.line(dressed)


RARE_ENTRIES = [
    {"rule_id": "34.8", "kind": "crew_fire", "data": {"vehicle": 3, "target": "C4", "firepower": 4, "roll": 5, "modifiers": [{"rule": "34.8", "value": 2, "cause": "the hull"}], "adjusted": 7, "result": "1"}},
    {"rule_id": "63.32", "kind": "heat_spent", "data": {"unit": 3, "roll": 6}},
    {"rule_id": "37.2", "kind": "flamethrower_infantry", "data": {"unit": 2, "target": "C4", "firepower": 20, "roll": 7, "modifiers": [], "adjusted": 7}},
    {"rule_id": "23.3", "kind": "demo_dud", "data": {"charge": 9, "unit": 2, "hex": "S1", "left_in": "R1"}},
    {"rule_id": "23.8", "kind": "demo_dud", "data": {"charge": 9, "roll": 12}},
    {"rule_id": "42.6", "kind": "stopped", "data": {"unit": 3, "hex": "B2", "tried": "C3"}},
    {"rule_id": "35.8", "kind": "pushed_out", "data": {"unit": 2, "vehicle": 3, "hex": "D5"}},
    {"rule_id": "13.5", "kind": "captured", "data": {"unit": 2, "weapon": 7, "from_player": 1}, "sides": {"0": "American", "1": "German"}},
    {"rule_id": "30.2", "kind": "vehicle_move", "data": {"unit": 3, "from": "B1", "to": "C1", "cost_halves": 3, "facing": 4, "rules": ["30.2", "29.4"]}},
    {"rule_id": "30.5", "kind": "vehicle_pivot", "data": {"unit": 3, "facing": 2, "was": 5}},
    {"rule_id": "18.5", "kind": "berserk_join_failed", "data": {"unit": 4, "leader": 5, "dice": [3, 3], "target": 3, "adjusted": 4}},
    {"rule_id": "20.3", "kind": "cc_kill", "data": {"player": 1, "leader": 6, "attackers": [6, 8], "targets": [2], "attack": 8, "defense": 4, "odds": "2-1", "kill": 7, "dice": [3, 1], "leadership": -1, "adjusted": 3}},
    {"rule_id": "33.3", "kind": "to_hit", "data": {"unit": 3, "target": "T3", "row": "infantry_in_woods", "raw": 2, "modifier": 4, "cases": ["D", "H"], "adjusted": 6, "needed": 8, "third_die": None, "hit": True}},
    {"rule_id": "host", "kind": "forced_command", "data": {"label": "end the phase", "player": 0}, "sides": {"0": "Russian", "1": "German"}},
]


def test_the_rare_events_show_their_fields():
    text = [logtext.line(e) for e in RARE_ENTRIES]
    assert "infantry fire hits the exposed crew" in text[0] and "roll 5" in text[0] and "+2 the hull (34.8)" in text[0]
    assert "last HEAT round" in text[1]
    assert "at C4" in text[2] and "20 firepower" in text[2]
    assert "left in R1" in text[3] and "at S1" in text[3]
    assert "roll 12" in text[4]
    assert "short of C3" in text[5] and "at B2" in text[5]
    assert "steps out" in text[6] and "at D5" in text[6]
    assert "from player German" in text[7]
    assert "facing south-west" in text[8] and "1.5 movement factors" in text[8] and "rules 30.2, 29.4" in text[8]
    assert "facing south-east" in text[9] and "was facing north-west" in text[9]
    assert "needs 3" in text[10]
    assert "attack 8 against defence 4" in text[11] and "odds 2-1, kill on 7" in text[11]
    assert "hit" in text[12] and "cases D, H" in text[12] and "needs 8" in text[12]
    assert "only legal command" in text[13] and "end the phase" in text[13]
    assert "roll" not in logtext.line(RARE_ENTRIES[0], tabletop=True)


# ------------------------------------------------------ the two logs, one text


def _game_lines() -> list[dict]:
    """The dressed log of real games: armour, and infantry with a leader."""
    lines: list[dict] = []
    for scenario, kind, seed in (("s04_armor_probe", "v3", 1), ("s01_guards_counterattack", "v1", 1)):
        engine = build_engine(scenario)
        record = play_game(engine, seed, (make_agent(kind, engine, seed, 0), make_agent(kind, engine, seed, 1)))
        state = engine.new_game(seed)
        names = annotate.Names()
        sides = annotate.side_names(engine)
        for index, event in enumerate(record.events):
            if index % 3 and event["kind"] in ("move", "group_add", "phase"):
                continue
            lines.append(annotate.dress_line(event, state, names, -1, sides))
    return lines + RARE_ENTRIES


def test_the_browser_log_and_the_desktop_log_give_the_same_text(tmp_path):
    node = shutil.which("node")
    if node is None or not ESBUILD.is_file():
        pytest.skip("node and the esbuild of the client are necessary for this comparison")
    bundle = tmp_path / "panel.mjs"
    try:
        subprocess.run(
            [str(ESBUILD), str(PANEL), "--bundle", "--format=esm", "--platform=node", f"--outfile={bundle}"],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise AssertionError(f"esbuild did not build the log panel: {exc}") from exc
    lines = _game_lines()
    kinds = {line["kind"] for line in lines}
    assert {"vehicle_move", "to_hit", "broken", "fire_result", "crew_fire", "stopped"} <= kinds
    corpus = tmp_path / "lines.json"
    corpus.write_text(json.dumps(lines), encoding="utf-8")
    runner = tmp_path / "run.mjs"
    runner.write_text(
        "import { readFileSync } from 'node:fs';\n"
        f"import {{ describe }} from {json.dumps(bundle.as_uri())};\n"
        f"const lines = JSON.parse(readFileSync({json.dumps(str(corpus))}, 'utf8'));\n"
        "const out = lines.map((e) => ({ full: describe(e, false), table: describe(e, true) }));\n"
        "process.stdout.write(JSON.stringify(out));\n",
        encoding="utf-8",
    )
    try:
        done = subprocess.run([node, str(runner)], check=True, capture_output=True, timeout=120, text=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise AssertionError(f"node did not run the log panel: {exc}") from exc
    browser = json.loads(done.stdout)
    assert len(browser) == len(lines)
    for line, shown in zip(lines, browser):
        assert shown["full"] == logtext.describe(line), (line, shown["full"])
        assert shown["table"] == logtext.describe(line, tabletop=True), (line, shown["table"])
