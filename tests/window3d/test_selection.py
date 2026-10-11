"""Tests for the click flow of the 3D window: a unit, then a hex, gives one legal command.

The frames are real. Two scripted agents play a game through the engine, and at each frame
the test asks the click flow for each legal command, from the view of the player that acts.
Each command with a hex must come from a click on the unit and a click on the hex. Each
command with no hex must be in the list beside the board. A command that no click reaches is
a command a person cannot play.

`slwindow3d.selection` imports no part of Panda3D, so these tests run with no window.
"""

from __future__ import annotations

import pytest

from slcli.play import build_engine, make_agent
from slcore import view as core_view
from slwindow3d.selection import (
    CLEAR,
    MENU,
    SELECT,
    SEND,
    Selection,
    describe,
    free_commands,
    payload,
    reserve_units,
    targets,
)


def _frames(scenario: str, seed: int, limit: int):
    """Each (legal list, view of the acting player, frame id) of a game of two v1 agents."""
    engine = build_engine(scenario, None)
    state = engine.new_game(seed)
    agents = {seat: make_agent("v1", engine, seed, seat) for seat in (0, 1)}
    count = 0
    while not state.game_over and count < limit:
        frame = engine.legal_commands(state)
        legal = frame.to_dict()["commands"]
        view = core_view.build(state, engine.types, state.active)
        yield legal, view, frame.frame_id
        chosen = agents[state.active].select(state, frame)
        state, _ = engine.apply(state, frame.by_id(chosen).command, frame)
        count += 1


def _reach(command, legal, view, frame_id) -> bool:
    """Play the clicks a person plays for this command, and say if they give it."""
    body = payload(command)
    hex_id = body.get("hex")
    if not hex_id:
        return command in free_commands(legal, None)
    units = [int(u) for u in body.get("units", [])]
    selection = Selection()
    selection.refresh(frame_id, legal, view)
    if not units:
        # A command to a hex that names no unit: a click on the hex, with no selection.
        selection.select(None)
        result = selection.click(hex_id, legal, view)
        if result.kind == SEND:
            return result.commands == (command,)
        return result.kind == MENU and command in result.commands
    waiting = reserve_units(legal, view)
    if selection.unit not in units and any(u in waiting for u in units):
        selection.select(next(u for u in units if u in waiting))
    if selection.unit not in units:
        on_board = {int(u["id"]): u.get("hex") for u in view["units"]}
        first = next((u for u in units if on_board.get(u)), None)
        if first is None:
            return False
        # Click the hex of the unit until that unit is the selection. Each click goes to
        # the next unit of the stack, so the number of clicks has a limit.
        for _ in range(len(view["units"]) + 1):
            result = selection.click(on_board[first], legal, view)
            if result.kind == MENU and first in result.units:
                result = selection.select(first)
            if result.kind == SELECT and selection.unit in units:
                break
        else:
            return False
    result = selection.click(hex_id, legal, view)
    if result.kind == SEND:
        return result.commands == (command,)
    if result.kind == MENU:
        return command in result.commands
    return False


@pytest.mark.parametrize(
    "scenario,seed,limit",
    [
        ("s01_guards_counterattack", 3, 900),
        ("s02_tractor_works", 4, 900),
        ("s03a_streets_of_stalingrad", 5, 900),
        ("s04_armor_probe", 2, 900),
    ],
)
def test_each_legal_command_is_reachable_by_clicks(scenario, seed, limit):
    missed: list[str] = []
    frames = 0
    commands = 0
    for legal, view, frame_id in _frames(scenario, seed, limit):
        frames += 1
        for command in legal:
            commands += 1
            if not _reach(command, legal, view, frame_id):
                missed.append(describe(command, view))
    assert frames > 100
    assert commands > frames
    assert not missed, f"{len(missed)} commands no click reaches, for example {missed[:5]}"


def test_set_up_selects_the_first_unit_to_place_with_no_click():
    legal, view, frame_id = next(_frames("s01_guards_counterattack", 1, 1))
    waiting = reserve_units(legal, view)
    assert waiting
    unit = waiting[0]
    selection = Selection()
    selection.refresh(frame_id, legal, view)
    assert selection.unit == unit
    hex_id, commands = next(iter(targets(legal, unit).items()))
    result = selection.click(hex_id, legal, view)
    assert result.kind == SEND
    assert result.commands == (commands[0],)


def test_a_click_on_an_empty_hex_with_no_command_clears_the_selection():
    for legal, view, frame_id in _frames("s01_guards_counterattack", 3, 900):
        if reserve_units(legal, view):
            continue
        movers = [c for c in legal if payload(c).get("action") == "move"]
        if not movers:
            continue
        unit = int(payload(movers[0])["units"][0])
        unit_hex = next(u["hex"] for u in view["units"] if int(u["id"]) == unit)
        selection = Selection()
        selection.refresh(frame_id, legal, view)
        assert selection.click(unit_hex, legal, view).kind == SELECT
        reachable = set(targets(legal, unit))
        occupied = {u.get("hex") for u in view["units"]}
        empty = next(
            h["id"]
            for h in core_view.board_document(build_engine("s01_guards_counterattack", None).board)["hexes"]
            if h["id"] not in reachable and h["id"] not in occupied
        )
        assert selection.click(empty, legal, view).kind == CLEAR
        assert selection.unit is None
        return
    pytest.fail("the game had no movement frame")


def test_the_selection_stays_on_a_unit_that_still_has_a_command_in_the_next_frame():
    selection = Selection()
    previous = None
    for legal, view, frame_id in _frames("s01_guards_counterattack", 3, 900):
        if previous is not None:
            selection.unit = previous
            selection.refresh(frame_id, legal, view)
            named = any(previous in [int(u) for u in payload(c).get("units", [])] for c in legal)
            if not reserve_units(legal, view):
                assert (selection.unit == previous) == named
        movers = [c for c in legal if payload(c).get("action") == "move"]
        previous = int(payload(movers[0])["units"][0]) if movers else None


def test_free_commands_put_the_selected_unit_first_then_the_commands_with_no_unit():
    for legal, view, frame_id in _frames("s01_guards_counterattack", 3, 900):
        no_hex = [c for c in legal if not payload(c).get("hex")]
        own = [c for c in no_hex if payload(c).get("units")]
        loose = [c for c in no_hex if not payload(c).get("units")]
        if not own or not loose:
            continue
        unit = int(payload(own[0])["units"][0])
        ordered = free_commands(legal, unit)
        assert len(ordered) == len(no_hex)
        assert unit in [int(u) for u in payload(ordered[0]).get("units", [])]
        first_loose = next(i for i, c in enumerate(ordered) if not payload(c).get("units"))
        assert all(unit in [int(u) for u in payload(c).get("units", [])] for c in ordered[:first_loose])
        return
    pytest.fail("the game had no frame with a unit command and a command with no unit")


def test_describe_names_the_units_and_the_target():
    legal, view, frame_id = next(_frames("s01_guards_counterattack", 1, 1))
    text = describe(legal[0], view)
    body = payload(legal[0])
    unit = next(u for u in view["units"] if int(u["id"]) == int(body["units"][0]))
    assert text.startswith("place ")
    assert (unit.get("name") or unit["type"]) in text
    assert text.endswith(f"to {body['hex']}")


def test_the_end_of_game_lines_name_the_winner_for_the_person():
    from types import SimpleNamespace

    from slwindow3d.selection import game_over_lines

    won = SimpleNamespace(result="russian", result_cause="the last turn is complete", turn=5)
    lost = SimpleNamespace(result="german", result_cause="", turn=3)
    drawn = SimpleNamespace(result="draw", result_cause="no side satisfied a victory condition", turn=5)
    assert game_over_lines(won, "russian") == ["You win", "the last turn is complete", "after turn 5. Press q to quit."]
    assert game_over_lines(lost, "russian")[0] == "German wins: you lose"
    # Hot seat or a watcher: no "you".
    assert game_over_lines(lost)[0] == "German wins"
    assert game_over_lines(drawn, "russian")[:2] == ["Draw", "no side satisfied a victory condition"]


def test_the_line_of_sight_line_names_the_answer_and_its_rule():
    from slwindow3d.selection import los_text

    clear = {"from": "C3", "to": "F4", "clear": True, "hindrance": 1, "rule_id": "7.1", "blocking_hex": None}
    blocked = {"from": "C3", "to": "F4", "clear": False, "hindrance": 0, "rule_id": "7.4", "blocking_hex": "D3"}
    assert los_text(clear) == "Line of sight C3 to F4: clear, hindrance +1 (rule 7.1)"
    assert los_text(blocked) == "Line of sight C3 to F4: blocked at D3 (rule 7.4)"
    assert los_text(None) == ""
