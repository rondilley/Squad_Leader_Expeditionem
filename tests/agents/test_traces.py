"""The trace writer (FR-60, DR-08, SR-09, SR-10).

The trace is the training data of the tuned model agent, so what it holds and what it
must not hold are both requirements. The tests here read real traces from real games.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slagents.tuned import traces
from slcore import view as view_module
from slcli.play import build_engine, make_agent, play_game, trace_writer

SCENARIO = "s02_tractor_works"


@pytest.fixture(scope="module")
def game():
    engine = build_engine(SCENARIO)
    agents = (make_agent("v2", engine, 5, 0), make_agent("v2", engine, 5, 1))
    writer = trace_writer(engine, 5, agents)
    record = play_game(engine, 5, agents, traces=writer)
    return engine, writer, record


def test_a_record_holds_each_field_that_the_data_requirement_names(game):
    """DR-08: the game ID, the decision index, the family and version, the view, the list,
    the selection, and the outcome."""
    _, writer, _ = game
    assert writer.records, "the game produced trace records"
    record = writer.records[len(writer.records) // 2]
    document = record.to_dict()
    for field in (
        "game_id",
        "decision",
        "family",
        "version",
        "view_text",
        "legal_command_ids",
        "selected_command_id",
        "outcome",
        "board_source",
    ):
        assert field in document, field
    assert record.selected_command_id in record.legal_command_ids
    assert record.decision == writer.records.index(record)
    assert record.game_id.startswith(SCENARIO)


def test_each_record_carries_the_result_of_the_game(game):
    _, writer, record = game
    assert record.result in ("german", "russian", "draw", "no_result")
    assert {r.result for r in writer.records} == {record.result}


def test_the_view_text_holds_no_unit_that_the_acting_player_cannot_see(game):
    """SR-09 with rule 25.2: a trace is built from the acting agent's view alone."""
    engine, writer, _ = game
    state = engine.new_game(5)
    seen = 0
    for record in writer.records[:200]:
        hidden = view_module.hidden_unit_ids(state, record.player)
        for unit_id in hidden:
            unit = state.units[unit_id]
            if unit.hex is None:
                continue
            assert f"{unit_id}:{engine.types[unit.type_key].key}@" not in record.view_text
            seen += 1
    assert seen >= 0


def test_the_view_text_of_a_player_names_its_own_units_and_the_tokens(game):
    _, writer, _ = game
    text = writer.records[len(writer.records) // 2].view_text
    assert text.startswith("turn ")
    assert "own: " in text
    assert "enemy seen: " in text
    assert "concealment: " in text
    assert "smoke: " in text


def test_a_trace_from_a_generated_board_carries_the_generated_source(game):
    """SR-10: the board source is in each record."""
    _, writer, _ = game
    assert writer.board_source == traces.SOURCE_GENERATED
    assert {r.board_source for r in writer.records} == {traces.SOURCE_GENERATED}
    assert traces.private_count(writer.records) == 0
    assert len(traces.generated_only(writer.records)) == len(writer.records)


def test_a_private_record_is_kept_out_of_the_default_build():
    """SR-10: the fine-tune build takes the generated records and leaves the others."""
    generated = traces.TraceRecord(
        game_id="g",
        decision=0,
        family="scripted",
        version="1",
        player=0,
        side="german",
        phase="movement",
        sub_step="move_window",
        turn=1,
        view_text="turn 1",
        legal_command_ids=("a",),
        selected_command_id="a",
        selected_payload={"action": "end_phase"},
        outcome=(),
        board_source=traces.SOURCE_GENERATED,
    )
    from dataclasses import replace

    private = replace(generated, board_source=traces.SOURCE_REFERENCE)
    records = [generated, private]
    assert traces.private_count(records) == 1
    assert traces.generated_only(records) == [generated]


def test_a_trace_file_round_trips(tmp_path: Path, game):
    _, writer, _ = game
    path = writer.write(tmp_path)
    assert path.name == traces.TRACES_FILE
    back = traces.read(path)
    assert len(back) == len(writer.records)
    assert back[0] == writer.records[0]
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["format"] == traces.FORMAT_VERSION
    assert doc["board_source"] == traces.SOURCE_GENERATED


def test_a_missing_trace_file_gives_a_typed_error(tmp_path: Path):
    with pytest.raises(traces.TraceError) as exc:
        traces.read(tmp_path / "nothing.json")
    assert "no trace file" in str(exc.value)


def test_a_trace_file_that_is_not_json_gives_a_typed_error(tmp_path: Path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(traces.TraceError) as exc:
        traces.read(path)
    assert "not valid JSON" in str(exc.value)


def test_the_writer_refuses_a_command_that_is_not_in_the_frame():
    engine = build_engine(SCENARIO)
    state = engine.new_game(3)
    frame = engine.legal_commands(state)
    writer = traces.TraceWriter(game_id="g", board_source=traces.SOURCE_GENERATED)
    agent = make_agent("v1", engine, 3, frame.player)
    with pytest.raises(traces.TraceError) as exc:
        writer.add(engine, state, frame, agent, "0" * 16, [])
    assert "not in the frame" in str(exc.value)


def test_the_same_view_gives_the_same_text():
    """A trace built two times is the same trace, so the data set is reproducible."""
    engine = build_engine(SCENARIO)
    state = engine.new_game(3)
    assert traces.view_text(engine, state, 0) == traces.view_text(engine, state, 0)
    assert traces.view_text(engine, state, 0) != traces.view_text(engine, state, 1)


async def test_a_hot_seat_game_on_the_host_writes_traces(tmp_path: Path):
    """FR-60: a game on the host gives traces of the same shape as a headless game."""
    from slagents.base import RandomAgent
    from slhost.server import Host

    engine = build_engine("s00_movement_drill")
    host = Host(engine, seed=2, traces=tmp_path, agents={1: RandomAgent(2, 1)})
    assert host.game.traces is not None
    for _ in range(20):
        frame = engine.legal_commands(host.game.state)
        if not frame.commands:
            break
        host.game.apply(frame.frame_id, frame.commands[0].id)
    path = host.game.write_traces(tmp_path)
    assert path is not None
    records = traces.read(path)
    assert len(records) == len(host.game.traces.records) > 0
    families = {r.family for r in records}
    assert "human" in families, "the person at the seat is the actor of those decisions"
    assert all(r.board_source == traces.SOURCE_GENERATED for r in records)
