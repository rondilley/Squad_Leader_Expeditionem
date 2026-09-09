"""The trace data set and its guard (FR-60, SR-10, TC-39).

TC-39 asks that the fine-tune command refuse a trace set that holds a `reference_private`
record, unless the owner gives the local-only flag. The guard is in two places: the data
set build refuses to write such a record, and the fine-tune refuses to read one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slagents.tuned import finetune, traces
from slcli.traces_cmd import GuardError, build, find_files, read_dataset, weight_of, write

GENERATED = traces.SOURCE_GENERATED
PRIVATE = traces.SOURCE_REFERENCE


def a_record(index: int, source: str = GENERATED, action: str = "move") -> traces.TraceRecord:
    return traces.TraceRecord(
        game_id=f"game-{source}",
        decision=index,
        family="scripted",
        version="1",
        player=0,
        side="german",
        phase="movement",
        sub_step="move_window",
        turn=1,
        view_text=f"turn 1 of 5 phase movement\nown: {index}",
        legal_command_ids=("aaaa", "bbbb"),
        selected_command_id="aaaa",
        selected_payload={"action": action, "units": [index]},
        outcome=("5.5:move",),
        board_source=source,
        result="german",
    )


def a_file(directory: Path, name: str, source: str, count: int = 3) -> Path:
    writer = traces.TraceWriter(game_id=f"game-{source}", board_source=source)
    writer.records = [a_record(i, source) for i in range(count)]
    return writer.write(directory, name)


def test_a_data_set_from_generated_traces_is_built(tmp_path: Path):
    a_file(tmp_path, "traces_1.json", GENERATED)
    samples, record = build(tmp_path)
    assert record["samples"] == 3
    assert record["games"] == 1
    assert record["private_records"] == 0
    assert all(s.board_source == GENERATED for s in samples)


def test_the_default_build_refuses_a_private_trace(tmp_path: Path):
    """TC-39: the guard names the file and does not write the data set."""
    a_file(tmp_path, "traces_1.json", GENERATED)
    private = a_file(tmp_path, "traces_2.json", PRIVATE)
    with pytest.raises(GuardError) as exc:
        build(tmp_path)
    message = str(exc.value)
    assert "reference-mode" in message
    assert private.name in message
    assert "--local-only" in message


def test_the_local_only_flag_accepts_a_private_trace(tmp_path: Path):
    """SR-10: the owner can build it, and the record says the data set is local only."""
    a_file(tmp_path, "traces_1.json", GENERATED)
    a_file(tmp_path, "traces_2.json", PRIVATE)
    samples, record = build(tmp_path, local_only=True)
    assert record["samples"] == 6
    assert record["local_only"] is True
    assert record["private_records"] == 3


def test_the_weight_of_a_decision_comes_from_what_it_was():
    """FR-61: a fire decision counts more than an end-phase decision."""
    fire = a_record(0, action="group_fire")
    end = a_record(1, action="end_phase")
    move = a_record(2, action="move")
    assert weight_of(fire) > weight_of(move) > weight_of(end)


def test_the_data_set_round_trips(tmp_path: Path):
    a_file(tmp_path, "traces_1.json", GENERATED)
    samples, _ = build(tmp_path)
    path = tmp_path / "data.jsonl"
    assert write(samples, path) == len(samples)
    back = read_dataset(path)
    assert len(back) == len(samples)
    assert back[0]["answer"] == samples[0].answer
    assert "prompt" in back[0] and "weight" in back[0]


def test_a_prompt_holds_the_view_and_the_legal_identities(tmp_path: Path):
    a_file(tmp_path, "traces_1.json", GENERATED)
    samples, _ = build(tmp_path)
    prompt = samples[0].prompt
    assert "turn 1 of 5" in prompt
    assert "aaaa" in prompt and "bbbb" in prompt


def test_the_fine_tune_refuses_a_private_record(tmp_path: Path):
    """TC-39: the second half of the guard, on the fine-tune itself."""
    a_file(tmp_path, "traces_1.json", PRIVATE)
    samples, _ = build(tmp_path, local_only=True)
    rows = [s.to_dict() for s in samples]
    with pytest.raises(finetune.FinetuneError) as exc:
        finetune.check_dataset(rows, finetune.Profile())
    assert "reference-mode" in str(exc.value)
    assert "SR-10" in str(exc.value)


def test_the_fine_tune_accepts_a_generated_record(tmp_path: Path):
    a_file(tmp_path, "traces_1.json", GENERATED)
    samples, _ = build(tmp_path)
    record = finetune.check_dataset([s.to_dict() for s in samples], finetune.Profile(), minimum_games=1)
    assert record["samples"] == 3
    assert record["enough_games"] is True


def test_the_profile_asks_for_two_hundred_games(tmp_path: Path):
    """NFR-09: the year-one profile names a minimum trace set."""
    a_file(tmp_path, "traces_1.json", GENERATED)
    samples, _ = build(tmp_path)
    record = finetune.check_dataset([s.to_dict() for s in samples], finetune.Profile())
    assert record["minimum_games"] == 200
    assert record["enough_games"] is False


def test_the_finder_reads_each_trace_file_under_a_directory(tmp_path: Path):
    a_file(tmp_path, "traces_1.json", GENERATED)
    nested = tmp_path / "run" / "deeper"
    nested.mkdir(parents=True)
    a_file(nested, "traces_2.json", GENERATED)
    assert len(find_files(tmp_path)) == 2
