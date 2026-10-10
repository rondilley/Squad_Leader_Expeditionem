"""The fine-tune smoke run (TR-12) and the export (IR-08).

TR-12 asks for fifty LoRA steps on ten traces with a finite loss, and for the exported
model to load on the local server. The first half runs here on a small model that the
module builds in memory. The second half needs llama.cpp and a running server, so the test
says what is missing and skips.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slagents.tuned import export, finetune, traces
from slcli.traces_cmd import build, write


def a_dataset(tmp_path: Path, count: int = 12) -> list[dict]:
    writer = traces.TraceWriter(game_id="game-1", board_source=traces.SOURCE_GENERATED)
    writer.records = [
        traces.TraceRecord(
            game_id="game-1",
            decision=i,
            family="scripted",
            version="1",
            player=i % 2,
            side="german",
            phase="movement",
            sub_step="move_window",
            turn=1,
            view_text=f"turn 1 of 5 phase movement\nown: unit {i} in B{i % 9 + 1}",
            legal_command_ids=("aaaa", "bbbb", "cccc"),
            selected_command_id="bbbb",
            selected_payload={"action": "move" if i % 2 else "group_fire", "units": [i]},
            outcome=(),
            board_source=traces.SOURCE_GENERATED,
            result="german",
        )
        for i in range(count)
    ]
    writer.write(tmp_path, "traces_1.json")
    samples, _ = build(tmp_path)
    return [s.to_dict() for s in samples]


def test_fifty_lora_steps_on_ten_traces_give_a_finite_loss(tmp_path: Path):
    """TR-12, first half. The loop, the weights, and the adapter."""
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    pytest.importorskip("peft")
    samples = a_dataset(tmp_path)
    record = finetune.run_smoke(samples, tmp_path / "out")
    assert record["steps"] == finetune.SMOKE_STEPS
    assert record["samples"] == finetune.SMOKE_SAMPLES
    assert record["finite_loss"] is True
    assert record["trainable_parameters"] > 0
    assert Path(record["adapter"]).is_dir()
    manifest = json.loads((tmp_path / "out" / finetune.MANIFEST_FILE).read_text(encoding="utf-8"))
    assert manifest["profile"]["name"] == "smoke"


def test_the_weight_of_a_decision_reaches_the_loss(tmp_path: Path):
    """FR-61: the batches carry the weight that the data set gave each decision."""
    samples = a_dataset(tmp_path)
    batches = finetune.smoke_batches(samples[: finetune.SMOKE_SAMPLES], finetune.SMOKE_PROFILE)
    weights = [w for _, group in batches for w in group]
    assert len(weights) == finetune.SMOKE_SAMPLES
    assert max(weights) > min(weights), "a fire decision and a move decision weigh differently"


def test_a_smoke_run_needs_a_sample(tmp_path: Path):
    with pytest.raises(finetune.FinetuneError) as exc:
        finetune.run_smoke([], tmp_path)
    assert "one sample" in str(exc.value)


def test_the_full_run_says_where_it_belongs(tmp_path: Path):
    """The deferred step gives an error that names what it waits for."""
    samples = a_dataset(tmp_path)
    with pytest.raises(finetune.FinetuneError) as exc:
        finetune.run_full(samples, tmp_path, finetune.Profile())
    message = str(exc.value)
    assert "owner's workstation" in message
    assert finetune.Profile().base_model in message


def test_the_export_says_what_is_missing(tmp_path: Path):
    """IR-08: each step of the export names what it needs."""
    pytest.importorskip("transformers")
    pytest.importorskip("peft")
    result = export.run_export(tmp_path / "no-adapter", "some/base", tmp_path)
    assert result.merged is None
    assert result.gguf is None
    assert any("no adapter directory" in note for note in result.notes)


def test_the_converter_is_named_when_it_is_absent(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(export.ENVIRONMENT_LLAMA_CPP, raising=False)
    monkeypatch.setattr(export.shutil, "which", lambda name: None)
    merged = tmp_path / "merged"
    merged.mkdir()
    with pytest.raises(export.ExportError) as exc:
        export.to_gguf(merged, tmp_path / "model.gguf")
    message = str(exc.value)
    assert export.CONVERTER in message
    assert export.ENVIRONMENT_LLAMA_CPP in message


@pytest.mark.integration
def test_the_exported_model_loads_on_the_local_server():
    """TR-12, second half. It needs a running llama-server with the exported file."""
    try:
        answer = export.load_on_server("the exported model")
    except export.ExportError as exc:
        pytest.skip(f"the local server is not serving the exported model: {exc}")
    assert answer["model"]
