"""The corrections of the review of 2026-09-23 to the learner and the prompted harness.

S12: a trace outcome holds the events the acting player may see. S13: the cycle guard of
the prompted harness keys a position by the player's view. L3: a league member plays one
whole game. L4: the evaluation plays seeds the training did not. L6: the model always sees
the command that ends the phase, and the parser takes the last balanced object. Each test
plays the real engine; none holds a substitute for the core.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from conformance.harness import build_case
from slagents.prompted import schema
from slagents.prompted.harness import MAX_COMMANDS_IN_PROMPT, position_key, shown_commands, text_state
from slagents.tuned import traces
from slcli.play import build_engine, make_agent
from slcore.view import event_visible

SCENARIO = "s01_guards_counterattack"


# ---------------------------------------------------------------------- S12


def test_a_trace_outcome_holds_only_the_events_the_acting_player_may_see():
    """S12: v2 against v2 on scenario 1 gives fire results on concealed stacks and the
    returns of rule 16.1 that the actor may not see. The record leaves them out, and the
    writer's own apply gives the same state as the game's."""
    engine = build_engine(SCENARIO)
    state = engine.new_game(1)
    agents = [make_agent("v2", engine, 1, p) for p in (0, 1)]
    writer = traces.TraceWriter(game_id="g", board_source=traces.SOURCE_GENERATED)
    dropped = 0
    steps = 0
    while not state.game_over and steps < 3000:
        frame = engine.legal_commands(state)
        chosen = agents[frame.player].select(state, frame)
        legal = frame.by_id(chosen)
        after, events = engine.apply(state, legal.command, frame)
        record = writer.add(engine, state, frame, agents[frame.player], chosen, events, after=after if steps % 2 else None)
        visible = [f"{e.rule_id}:{e.kind}" for e in events if event_visible(after, {"kind": e.kind, "data": e.data}, frame.player)]
        assert list(record.outcome) == visible
        dropped += len(events) - len(visible)
        state = after
        steps += 1
    assert dropped > 0, "the game had events the actor may not see, and the traces left them out"


# ---------------------------------------------------------------------- S13


def test_the_cycle_guard_key_reads_the_view_and_not_the_hidden_units():
    """S13: two states that differ in a hidden enemy unit alone are one position for the
    player who cannot see it, and two positions for its owner."""
    built = build_case(
        {
            "phase": "prep_fire",
            "sub_step": "fire_window",
            "phasing": "german",
            "active": "german",
            "units": [
                {"ref": "own", "side": "german", "type": "4-6-7", "hex": "A1"},
                {"ref": "hid", "side": "russian", "type": "4-4-7", "hex": "C3", "hidden": True},
            ],
        }
    )
    engine = built.engine
    german = engine.scenario.side_index("german")
    other = built.state.with_unit(replace(built.unit("hid"), hex=(4, 4)))
    types = engine.types
    assert other.to_dict() != built.state.to_dict()
    assert position_key(other, types, german) == position_key(built.state, types, german)
    assert position_key(other, types, 1 - german) != position_key(built.state, types, 1 - german)


# ----------------------------------------------------------------------- L6


def _large_frame():
    """A Movement Phase of scenario 2 with more commands than the prompt lists."""
    engine = build_engine("s02_tractor_works")
    state = engine.new_game(3)
    agents = [make_agent("v1", engine, 3, p) for p in (0, 1)]
    for _ in range(3000):
        frame = engine.legal_commands(state)
        if len(frame.commands) > MAX_COMMANDS_IN_PROMPT and any(lc.command.action == "end_phase" for lc in frame.commands):
            return engine, state, frame
        state, _ = engine.apply(state, frame.by_id(agents[frame.player].select(state, frame)).command, frame)
    raise AssertionError("no frame above the limit of the prompt")


def test_the_model_always_sees_the_command_that_ends_the_phase():
    """L6: the core puts end_phase last, and the cut of the list at 120 took it away."""
    engine, state, frame = _large_frame()
    end = next(lc for lc in frame.commands if lc.command.action == "end_phase")
    assert frame.commands.index(end) >= MAX_COMMANDS_IN_PROMPT, "the frame puts the end past the cut"
    shown = shown_commands(frame.commands)
    assert len(shown) == MAX_COMMANDS_IN_PROMPT and end in shown
    text = text_state(engine, state, frame, frame.player, [])
    assert end.id in text
    assert f"... and {len(frame.commands) - MAX_COMMANDS_IN_PROMPT} more" in text


def test_the_parser_takes_the_last_balanced_object():
    """L6: an analysis with braces of its own does not spoil the answer."""
    text = (
        "I see the stacks {A1, B2} and {C3}. The plan: hold.\n"
        + json.dumps({schema.COMMAND_FIELD: "abc", "plan": "brace } in a string", "reason": "r {x}"})
        + "\nThat is all."
    )
    decision = schema.parse(text, ["abc", "def"])
    assert decision.command_id == "abc" and decision.plan == "brace } in a string"
    two = json.dumps({schema.COMMAND_FIELD: "def"}) + " then " + json.dumps({schema.COMMAND_FIELD: "abc", "plan": "", "reason": ""})
    assert schema.parse(two, ["abc", "def"]).command_id == "abc", "the last object is the answer"
    nested = 'x {"command_id": "abc", "plan": "p", "reason": "{\\"q\\": 1}"}'
    assert schema.parse(nested, ["abc"]).reason == '{"q": 1}'
    with pytest.raises(schema.SchemaError):
        schema.parse("no object {here", ["abc"])
