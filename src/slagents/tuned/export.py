"""Merge the adapter and put the model on the local server (IR-08).

The tuned model plays on the same llama-server as the prompted local model, so the export
has three steps:

1. Merge the LoRA adapter into the base model. `peft` does that, and the result is an
   ordinary model directory.
2. Convert that directory to GGUF, which is the format llama-server reads. The converter
   is `convert_hf_to_gguf.py` from llama.cpp. It is not a Python package, so this module
   looks for it and says where to get it when it is not on the machine.
3. Load it on the server and ask one question, which is the second half of TR-12.

Each step gives an error that names what is missing, and no step writes a file that a
later step would read as complete.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONVERTER = "convert_hf_to_gguf.py"
ENVIRONMENT_LLAMA_CPP = "LLAMA_CPP_HOME"
MERGED = "merged"
GGUF_SUFFIX = ".gguf"


class ExportError(Exception):
    """The export could not finish. The message says what is missing."""


@dataclass(frozen=True)
class ExportResult:
    """What the export produced."""

    merged: Path | None
    gguf: Path | None
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "merged": str(self.merged) if self.merged else None,
            "gguf": str(self.gguf) if self.gguf else None,
            "notes": list(self.notes),
        }


def merge(adapter: Path, base_model: str, out: Path) -> Path:
    """Step one: the adapter and the base become one model directory."""
    try:
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise ExportError(
            "the merge needs the `finetune` extra: pip install -e \".[finetune]\" for "
            "transformers and peft"
        ) from exc
    if not adapter.is_dir():
        raise ExportError(f"there is no adapter directory at {adapter}")
    try:
        model = AutoModelForCausalLM.from_pretrained(base_model)
        merged = PeftModel.from_pretrained(model, str(adapter)).merge_and_unload()
    except Exception as exc:  # the base model can be absent, or too large for this machine
        raise ExportError(f"cannot merge the adapter into {base_model}: {exc}") from exc
    target = out / MERGED
    target.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(str(target))
    try:
        AutoTokenizer.from_pretrained(base_model).save_pretrained(str(target))
    except Exception:
        # A model that this project built in memory has no tokenizer of its own, and the
        # converter of step two reads the model files, not the tokenizer.
        pass
    return target


def converter_path() -> Path | None:
    """Where `convert_hf_to_gguf.py` is, from the environment variable or the path."""
    home = os.environ.get(ENVIRONMENT_LLAMA_CPP)
    if home:
        candidate = Path(home) / CONVERTER
        if candidate.is_file():
            return candidate
    found = shutil.which(CONVERTER)
    return Path(found) if found else None


def to_gguf(merged: Path, out_file: Path, quantization: str = "f16") -> Path:
    """Step two: the model directory becomes one GGUF file that llama-server reads."""
    converter = converter_path()
    if converter is None:
        raise ExportError(
            f"cannot find {CONVERTER}. It comes with llama.cpp, and this build does not ship it. "
            f"Clone llama.cpp and set {ENVIRONMENT_LLAMA_CPP} to its directory, then run the export again."
        )
    if not merged.is_dir():
        raise ExportError(f"there is no merged model at {merged}")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(converter), str(merged), "--outfile", str(out_file), "--outtype", quantization]
    try:
        finished = subprocess.run(command, capture_output=True, text=True, timeout=3600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExportError(f"the converter did not finish: {exc}") from exc
    if finished.returncode != 0:
        raise ExportError(f"the converter gave {finished.returncode}: {finished.stderr[-400:]}")
    if not out_file.is_file():
        raise ExportError(f"the converter wrote no file at {out_file}")
    return out_file


def load_on_server(model_name: str, provider_name: str = "local") -> dict[str, Any]:
    """Step three: the server answers with the exported model (IR-08, TR-12)."""
    from slagents.prompted.providers import ProviderError, load_config, make_provider

    config = load_config()
    provider = make_provider(provider_name, config)
    if not provider.health():
        raise ExportError(
            f"the local server does not answer. Start llama-server with the exported file and "
            f"the model name {model_name}, then run this step again."
        )
    try:
        answer = provider.complete("You answer in one word.", "Reply with the single word: ready", max_tokens=8)
    except ProviderError as exc:
        raise ExportError(f"the local server did not answer a question: {exc}") from exc
    return {"model": answer.model, "seconds": answer.seconds, "text": answer.text[:40]}


def run_export(adapter: Path, base_model: str, out: Path, quantization: str = "f16") -> ExportResult:
    """The three steps, with a note for each one that could not run here."""
    notes: list[str] = []
    merged: Path | None = None
    gguf: Path | None = None
    try:
        merged = merge(adapter, base_model, out)
    except ExportError as exc:
        notes.append(f"merge: {exc}")
        return ExportResult(None, None, tuple(notes))
    try:
        gguf = to_gguf(merged, out / f"{Path(base_model).name}{GGUF_SUFFIX}", quantization)
    except ExportError as exc:
        notes.append(f"gguf: {exc}")
    return ExportResult(merged, gguf, tuple(notes))
