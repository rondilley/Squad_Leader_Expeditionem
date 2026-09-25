"""The command choice and the log text of the two desktop windows (H7, H8, slice 8).

`slwindow.choice` holds the list a person sees, the cursor, and the board choice, and
`slwindow.logtext` holds the text of one log entry. Neither has a game library, so these
tests read them with no screen. The legal lists come from the real engine, and the
version 2 entries from the real host annotation, so the model is proved on what a host
sends and not on a list this file made up.
"""

from __future__ import annotations

import pytest

from slcli.play import build_engine, make_agent
from slcore import view as core_view
from slhost import annotate
from slwindow import choice, logtext
from slwindow.overlay import next_focus, position_of


def _play_to(engine, seed: int, test, limit: int = 4000):
    """Play two v1 agents until `test(state, frame)` is true, and give that position."""
    state = engine.new_game(seed)
    agents = {p: make_agent("v1", engine, seed, p) for p in (0, 1)}
    for _ in range(limit):
        frame = engine.legal_commands(state)
        if test(state, frame):
            return state, frame
        if state.game_over:
            break
        chosen = agents[state.active].select(state, frame)
        state, _events = engine.apply(state, frame.by_id(chosen).command, frame)
    raise AssertionError("the game did not reach the position the test needs")


@pytest.fixture(scope="module")
def movement():
    """A movement frame of scenario 1 where a unit has more than one move, as version 1
    entries (the payload only) and as version 2 entries (labels, units, hexes, odds)."""
    engine = build_engine("s01_guards_counterattack")

    def wanted(state, frame):
        if state.phase != "movement":
            return False
        moves = [lc for lc in frame.commands if lc.command.action == "move"]
        return len({lc.command.units for lc in moves}) >= 2 and len(moves) >= 6

    state, frame = _play_to(engine, 7, wanted)
    view = core_view.build(state, engine.types, frame.player)
    v1 = [{"id": lc.id, "payload": lc.payload} for lc in frame.commands]
    v2 = annotate.legal_entries(engine, state, frame, annotate.Names(), frame.player, True)
    return engine, state, frame, view, v1, v2


# ---------------------------------------------------------------- the entries


def test_a_version_1_entry_and_a_version_2_entry_give_the_same_units_and_hex(movement):
    _engine, _state, _frame, _view, v1, v2 = movement
    for old, new in zip(v1, v2):
        assert choice.unit_ids(old) == choice.unit_ids(new)
        if old["payload"].get("hex"):
            assert choice.hexes_of(old)[0] in choice.hexes_of(new)


def test_the_row_text_is_the_host_label_with_the_odds(movement):
    _engine, _state, _frame, view, _v1, v2 = movement
    entry = next(e for e in v2 if e["action"] == "move")
    text = choice.row_text(entry, view)
    assert text.startswith(entry["label"])
    if "odds" in entry:
        assert "break" in text and "%" in text


def test_the_odds_are_whole_percents_with_integer_arithmetic():
    fire = {"odds": {"kind": "fire", "kia": 36, "k": 72, "break": 648, "of": 1296}}
    assert choice.odds_text(fire) == "KIA 3% K 6% break 50%"
    assert choice.odds_text({"odds": {"kind": "move", "break_worst": 1296, "of": 1296}}) == "break 100% at worst"
    assert choice.odds_text({"odds": {"kind": "close_combat", "kill": 0, "killed": 1295}}) == "kill 0% killed 100%"
    assert choice.odds_text({"odds": {"kind": "rally", "rally": 540}}) == "rally 42%"
    assert choice.odds_text({"id": "x"}) == ""


def test_a_version_1_entry_names_its_units_from_the_view(movement):
    _engine, _state, _frame, view, v1, _v2 = movement
    entry = next(e for e in v1 if e["payload"]["action"] == "move")
    unit = next(u for u in view["units"] if u["id"] == entry["payload"]["units"][0])
    assert unit["name"] in choice.label_of(entry, view)


# ------------------------------------------------------------------- the list


def test_the_filter_narrows_the_list_and_enter_takes_the_filtered_row(movement):
    """H7: the cursor reads the list a person sees, not the full list."""
    _engine, _state, _frame, view, _v1, v2 = movement
    chooser = choice.Chooser()
    chooser.sync("f1", v2)
    target = next(i for i, e in enumerate(v2) if e["action"] == "end_phase")
    chooser.type("end")
    rows = chooser.visible(v2, view)
    assert rows and all("end" in choice.row_text(e, view).lower() or "end" in choice.describe(e) for _i, e in rows)
    assert chooser.selected(v2, view) == rows[0][0]
    assert target in [i for i, _e in rows]
    assert chooser.selected(v2, view) != 0 or v2[0]["action"] == "end_phase"


def test_a_new_frame_puts_the_cursor_at_the_top_and_keeps_the_unit(movement):
    _engine, _state, _frame, view, _v1, v2 = movement
    chooser = choice.Chooser()
    chooser.sync("f1", v2)
    unit = choice.unit_ids(next(e for e in v2 if e["action"] == "move"))[0]
    chooser.unit = unit
    chooser.move(3, v2, view)
    chooser.hex = "A1"
    assert chooser.sync("f1", v2) is False, "the same frame is not new"
    assert chooser.sync("f2", v2) is True
    assert chooser.position == 0 and chooser.scroll == 0
    assert chooser.hex is None, "a new frame drops the hex of the board choice"
    assert chooser.unit == unit, "the unit stays while it has a command"
    chooser.sync("f3", [e for e in v2 if unit not in choice.unit_ids(e)])
    assert chooser.unit is None, "a unit with no command in the new list is dropped"


def test_the_list_scrolls_so_the_cursor_stays_on_the_screen():
    legal = [{"id": str(i), "payload": {"action": "move", "units": [i], "hex": f"A{i}"}} for i in range(60)]
    chooser = choice.Chooser()
    chooser.page_rows = 10
    chooser.move(45, legal)
    assert chooser.position == 45
    assert chooser.scroll <= 45 < chooser.scroll + chooser.page_rows
    chooser.page(-1, legal)
    assert chooser.scroll <= chooser.position < chooser.scroll + chooser.page_rows
    chooser.scroll_by(100, legal)
    assert chooser.scroll == 50, "the wheel stops at the last page"
    chooser.move(100, legal)
    assert chooser.position == 59


def test_escape_clears_the_filter_then_the_hex_then_the_unit():
    chooser = choice.Chooser()
    chooser.filter_text = "mo"
    chooser.hex = "B2"
    chooser.unit = 4
    assert chooser.escape() == "filter"
    assert chooser.escape() == "hex"
    assert chooser.escape() == "unit"
    assert chooser.escape() == ""


# ----------------------------------------------------------- the board choice


def test_a_click_pins_a_unit_and_a_click_on_its_hex_option_chooses(movement):
    """Slice 8: click a unit, then click a hex that one of its commands names."""
    _engine, _state, _frame, view, _v1, v2 = movement
    moves = [e for e in v2 if e["action"] == "move"]
    counts: dict[tuple[int, str], int] = {}
    for entry in moves:
        for hex_id in choice.hexes_of(entry):
            key = (choice.unit_ids(entry)[0], hex_id)
            counts[key] = counts.get(key, 0) + 1
    (unit, destination) = next(key for key, count in counts.items() if count == 1)
    home = position_of(next(u for u in view["units"] if u["id"] == unit))
    chooser = choice.Chooser()
    chooser.sync("f1", v2)
    # The first click pins a unit of the hex. Clicks on the same hex walk the stack.
    pinned = None
    for _ in range(8):
        picked = chooser.board_click(view, v2, home, pinned, next_focus)
        assert picked.send is None, "a click on the hex of the pinned unit never sends"
        pinned = picked.pinned
        if pinned == unit:
            break
    assert pinned == unit
    assert chooser.unit == unit
    shown = chooser.visible(v2, view)
    assert shown and all(unit in choice.unit_ids(e) for _i, e in shown)
    picked = chooser.board_click(view, v2, destination, pinned, next_focus)
    expected = next(i for i, e in enumerate(v2) if e["action"] == "move" and unit in choice.unit_ids(e) and destination in choice.hexes_of(e))
    assert picked.send == expected
    assert picked.pinned == unit


def test_a_click_on_a_hex_that_names_no_command_of_the_pinned_unit_sends_nothing(movement):
    _engine, _state, _frame, view, _v1, v2 = movement
    chooser = choice.Chooser()
    unit = choice.unit_ids(next(e for e in v2 if e["action"] == "move"))[0]
    named = {h for e in v2 if unit in choice.unit_ids(e) for h in choice.hexes_of(e)}
    occupied = {position_of(u) for u in view["units"]}
    empty = next(h["id"] for h in core_view.board_document(movement[0].board)["hexes"] if h["id"] not in named | occupied)
    picked = chooser.board_click(view, v2, empty, unit, next_focus)
    assert picked.send is None
    assert picked.pinned is None, "a click on an empty hex clears the pin"


# -------------------------------------------------------------------- the log


def test_the_log_line_shows_the_dice_the_modifiers_the_units_and_the_hexes():
    """FR-06: the same fields as the browser log, and the morale modifier (H8)."""
    broken = {
        "rule_id": "12.3",
        "kind": "broken",
        "data": {"unit": 27, "hex": "B6", "dice": [5, 2], "modifier": 2, "leadership": -1, "leader": 25, "adjusted": 8, "morale": 7, "cause": "fire"},
        "names": {"27": "4-4-7 #3 (B6)", "25": "9-1 Petrov (B6)"},
        "sides": {"0": "Russian", "1": "German"},
    }
    text = logtext.line(broken)
    for part in ("12.3", "broken", "at B6", "4-4-7 #3 (B6)", "9-1 Petrov (B6)", "dice 5 and 2", "modifier +2", "leader -1", "adjusted 8", "morale 7", "fire"):
        assert part in text, (part, text)
    rally = {"rule_id": "14.2", "kind": "rallied", "data": {"unit": 27, "hex": "B6", "dice": [1, 3], "target": 3, "adjusted": 3}}
    text = logtext.line(rally)
    assert "at B6" in text and "needs 3" in text and "unit #27" in text
    fire = {
        "rule_id": "10.5",
        "kind": "fire_result",
        "data": {"target": "H6", "adjusted": 12, "firepower": 18, "result": "-", "units": [39], "modifiers": [{"value": -1, "cause": "hindrance", "rule": "10.4"}]},
    }
    text = logtext.line(fire)
    assert "18 firepower" in text and "-1 hindrance (10.4)" in text and "at H6" in text
    assert "dice" not in logtext.line(broken, tabletop=True), "the tabletop switch hides the dice"


def test_a_side_number_in_the_log_shows_the_side_name():
    entry = {"rule_id": "4", "kind": "turn_start", "data": {"turn": 2, "phasing": 1}, "sides": {"0": "Russian", "1": "German"}}
    assert "German" in logtext.line(entry)


# ----------------------------------------------------------------- the client


def _frame(player: int, frame_id: str, lines: list[dict], **extra) -> dict:
    message = {
        "type": "frame",
        "player": player,
        "view": {"units": []},
        "frame_id": frame_id,
        "active": player,
        "phase": "movement",
        "sub_step": "move",
        "turn": 1,
        "legal_commands": [],
        "log_tail": lines,
    }
    message.update(extra)
    return message


def test_the_client_keeps_one_log_for_each_viewer_and_merges_by_seq():
    """Protocol version 2: hot seat has one log stream for each side, each with its own
    `seq`, and a frame can send a line again (the history after a reconnect)."""
    from slwindow.client import HostClient

    client = HostClient("ws://127.0.0.1:1/", "none")
    line = lambda seq, kind: {"rule_id": "5.5", "kind": kind, "data": {}, "seq": seq}  # noqa: E731
    client._receive(_frame(0, "a", [line(0, "a0"), line(1, "a1")]))
    client._receive(_frame(1, "b", [line(0, "b0")]))
    assert [e["kind"] for e in client.snapshot().log] == ["b0"]
    client._receive(_frame(0, "c", [line(1, "a1"), line(2, "a2")]))
    assert [e["kind"] for e in client.snapshot().log] == ["a0", "a1", "a2"]


def test_the_client_reads_the_new_fields_of_a_frame_and_of_the_end():
    from slwindow.client import STATUS_GAME_OVER, STATUS_THINKING, HostClient, status_of

    client = HostClient("ws://127.0.0.1:1/", "none")
    client._receive(
        {
            "type": "welcome",
            "player": 0,
            "you": 0,
            "seat": "hot_seat",
            "board": {"hexes": []},
            "scenario": {"players": ["russian", "german"]},
            "sides": {"0": {"name": "Russian", "controller": "human"}, "1": {"name": "German", "controller": "computer"}},
            "seat_token": "ab" * 16,
        }
    )
    assert client._seat_token == "ab" * 16
    assert "seat_token" not in vars(client.snapshot()), "the token is not in what the window draws"
    client._receive(_frame(0, "a", [], status=STATUS_THINKING, auto_applied=["end the phase"], can_undo=True, phase_text="Move."))
    snapshot = client.snapshot()
    assert status_of(snapshot) == STATUS_THINKING
    assert snapshot.auto_applied == ["end the phase"] and snapshot.can_undo and snapshot.phase_text == "Move."
    assert snapshot.sides["1"]["controller"] == "computer"
    client._receive({"type": "game_over", "result": 1, "winner_name": "German", "cause": "c", "conditions": [], "turn": 6, "casualties": {}})
    snapshot = client.snapshot()
    assert snapshot.game_over and status_of(snapshot) == STATUS_GAME_OVER and snapshot.over["winner_name"] == "German"


def test_each_error_code_has_its_own_text_and_only_a_terminal_code_ends_the_session():
    """H6: a message for each code, and no new try after a terminal one."""
    from slwindow.client import ERROR_TEXT, TERMINAL_CODES, HostClient

    for code in ERROR_TEXT:
        client = HostClient("ws://127.0.0.1:1/", "none")
        client._receive({"type": "error", "rule_id": "SR-03", "message": "from the host", "code": code})
        snapshot = client.snapshot()
        assert snapshot.notice.startswith(ERROR_TEXT[code]) and "from the host" in snapshot.notice
        assert snapshot.error_code == code
        assert (client._terminal is not None) == (code in TERMINAL_CODES), code
    assert TERMINAL_CODES == {"room_code", "rate_limited", "origin", "room_full"}


def test_the_client_knows_each_error_code_and_each_status_of_the_host():
    """The window and the host agree on the closed sets of protocol version 2."""
    from slhost import protocol
    from slwindow.client import ERROR_TEXT, STATUS_TEXT, TERMINAL_CODES

    assert set(ERROR_TEXT) == set(protocol.ERROR_CODES)
    assert TERMINAL_CODES == set(protocol.TERMINAL_CODES)
    statuses = {protocol.STATUS_YOUR_TURN, protocol.STATUS_WAITING, protocol.STATUS_COMPUTER, protocol.STATUS_GAME_OVER}
    assert set(STATUS_TEXT) == statuses
