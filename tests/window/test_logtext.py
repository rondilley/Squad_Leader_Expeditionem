"""The action log lines (BC-04): each event with dice shows its rule, its dice, its modifier,
and its total. The events come from a real game of two v1 agents."""

from __future__ import annotations

from slcli.play import build_engine, make_agent
from slwindow.logtext import log_text


def _events(seed: int):
    engine = build_engine("s01_guards_counterattack")
    state = engine.new_game(seed)
    agents = {seat: make_agent("v1", engine, seed, seat) for seat in (0, 1)}
    while not state.game_over:
        frame = engine.legal_commands(state)
        state, events = engine.apply(state, frame.by_id(agents[state.active].select(state, frame)).command, frame)
        for event in events:
            yield event.to_dict()


def test_each_event_with_dice_shows_the_rule_the_dice_and_the_total():
    kinds = set()
    for entry in _events(seed=3):
        data = entry["data"]
        line = log_text(entry)
        assert line.startswith(str(entry["rule_id"])) or entry["kind"] == "game_end"
        if data.get("dice"):
            kinds.add(entry["kind"])
            assert "+".join(str(d) for d in data["dice"]) in line, line
            assert f"= {data['adjusted']}" in line, line
    # A whole game has fire, morale checks, and close combat.
    assert {"fire", "broken"} <= kinds or {"fire", "morale_pass"} <= kinds


def test_a_fire_line_gives_the_modifier_the_dice_do_not():
    entry = {
        "rule_id": "10.6",
        "kind": "fire",
        "data": {"target": "H6", "firepower": 12, "column": 12, "dice": [3, 4], "adjusted": 9},
    }
    assert log_text(entry) == "10.6 fire at H6: 12 FP col 12, dice 3+4 DRM +2 = 9"


def test_a_result_line_names_the_units_by_the_names_it_gets():
    entry = {"rule_id": "10.5", "kind": "fire_result", "data": {"target": "H6", "result": "2", "units": [39, 40]}}
    assert log_text(entry, {39: "Sgt Kelso"}) == "10.5 H6: MC+2 on Sgt Kelso, unit 40"
