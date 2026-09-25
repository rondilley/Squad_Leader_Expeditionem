"""The fine-tune of the tuned model agent (FR-61, NFR-09, TR-12).

The year-one profile is fixed and named, because a profile that changes between runs makes
two runs uncomparable: a base model of 7B or 8B parameters, LoRA on the attention
projections, a fixed context length, generated traces only, and a trace set of a minimum of
200 games (NFR-09).

The path has three steps, and each one has to work before the next one starts:

1. The smoke run. Fifty LoRA steps on ten traces, with a finite loss (TR-12). It runs on a
   small model that this module builds in memory, so it needs no download and no GPU. What
   it proves is the loop: the data set reads, the weights of FR-61 reach the loss, the
   gradient flows through the LoRA parameters, and the adapter saves and loads.
2. The export and the load. `export.py` merges the adapter and writes the files that
   llama-server reads (IR-08).
3. The full run on the owner's workstation with the year-one profile.

The importance weight of FR-61 is in the loss. A fire decision counts three times an
end-phase decision, because the trace command builds the weight and this module reads it.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

MINIMUM_GAMES = 200
SMOKE_STEPS = 50
SMOKE_SAMPLES = 10
ADAPTER_FILE = "adapter"
MANIFEST_FILE = "finetune.json"


class FinetuneError(Exception):
    """The fine-tune cannot run with what it was given."""


@dataclass(frozen=True)
class Profile:
    """The year-one profile of NFR-09. A run artifact records it."""

    name: str = "year-one"
    base_model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct"
    context_length: int = 2048
    lora_rank: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: tuple[str, ...] = ("q_proj", "k_proj", "v_proj", "o_proj")
    learning_rate: float = 1e-4
    batch_size: int = 4
    steps: int = 2000
    quantized: bool = True
    generated_traces_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "base_model": self.base_model,
            "context_length": self.context_length,
            "lora_rank": self.lora_rank,
            "lora_alpha": self.lora_alpha,
            "lora_dropout": self.lora_dropout,
            "target_modules": list(self.target_modules),
            "learning_rate": self.learning_rate,
            "batch_size": self.batch_size,
            "steps": self.steps,
            "quantized": self.quantized,
            "generated_traces_only": self.generated_traces_only,
        }


SMOKE_PROFILE = Profile(
    name="smoke",
    base_model="in-memory-small",
    context_length=128,
    lora_rank=4,
    lora_alpha=8,
    target_modules=("c_attn",),
    learning_rate=1e-3,
    batch_size=2,
    steps=SMOKE_STEPS,
    quantized=False,
)


def check_dataset(samples: Sequence[dict[str, Any]], profile: Profile, minimum_games: int = MINIMUM_GAMES) -> dict[str, Any]:
    """What the data set holds, and whether the profile accepts it (SR-10, NFR-09)."""
    if not samples:
        raise FinetuneError("the data set is empty")
    private = [s for s in samples if s.get("board_source") != "generated"]
    if private and profile.generated_traces_only:
        raise FinetuneError(
            f"{len(private)} samples come from a reference-mode board, and the profile "
            f"{profile.name!r} takes generated traces only (SR-10). Build the data set again "
            "without them, or use a profile that the owner marked local-only."
        )
    games = {s.get("game_id") for s in samples}
    record = {
        "samples": len(samples),
        "games": len(games),
        "weight_total": round(sum(float(s.get("weight", 1.0)) for s in samples), 2),
        "minimum_games": minimum_games,
        "enough_games": len(games) >= minimum_games,
    }
    return record


def character_ids(text: str, length: int) -> list[int]:
    """A byte view of the text for the smoke model, which has no tokenizer of its own."""
    data = text.encode("utf-8")[: length]
    return list(data) if data else [0]


def smoke_batches(samples: Sequence[dict[str, Any]], profile: Profile) -> list[tuple[list[list[int]], list[float]]]:
    """The batches of the smoke run: byte sequences and their weights."""
    rows = []
    for sample in samples:
        text = f"{sample['prompt']}\n{sample['answer']}"
        rows.append((character_ids(text, profile.context_length), float(sample.get("weight", 1.0))))
    batches = []
    for start in range(0, len(rows), profile.batch_size):
        chunk = rows[start : start + profile.batch_size]
        width = max(len(ids) for ids, _ in chunk)
        padded = [ids + [0] * (width - len(ids)) for ids, _ in chunk]
        batches.append((padded, [weight for _, weight in chunk]))
    return batches


def smoke_model(profile: Profile):
    """A small language model in memory, with LoRA on its attention (TR-12).

    The model is built here and not downloaded, so the smoke run needs no network and no
    GPU. It is a real model with real gradients, and it is not the year-one base.
    """
    try:
        import torch
        from peft import LoraConfig, get_peft_model
        from transformers import GPT2Config, GPT2LMHeadModel
    except ImportError as exc:  # pragma: no cover - the message names the tier
        raise FinetuneError(
            "the fine-tune needs the `finetune` extra: pip install -e \".[finetune]\" for "
            "torch, transformers, and peft"
        ) from exc
    config = GPT2Config(
        vocab_size=256,
        n_positions=profile.context_length,
        n_embd=64,
        n_layer=2,
        n_head=2,
    )
    model = GPT2LMHeadModel(config)
    lora = LoraConfig(
        r=profile.lora_rank,
        lora_alpha=profile.lora_alpha,
        lora_dropout=profile.lora_dropout,
        target_modules=list(profile.target_modules),
        task_type="CAUSAL_LM",
    )
    return get_peft_model(model, lora)


def run_smoke(samples: Sequence[dict[str, Any]], out: Path, profile: Profile | None = None) -> dict[str, Any]:
    """TR-12, first half: fifty LoRA steps on ten traces with a finite loss."""
    settings = profile or SMOKE_PROFILE
    chosen = list(samples)[:SMOKE_SAMPLES]
    if not chosen:
        raise FinetuneError("the smoke run needs one sample or more")
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - the message names the tier
        raise FinetuneError(
            "the fine-tune needs the `finetune` extra: pip install -e \".[finetune]\" for "
            "torch, transformers, and peft"
        ) from exc

    model = smoke_model(settings)
    trainable = [p for p in model.parameters() if p.requires_grad]
    if not trainable:
        raise FinetuneError("the LoRA configuration left no parameter to train")
    optimizer = torch.optim.AdamW(trainable, lr=settings.learning_rate)
    batches = smoke_batches(chosen, settings)
    losses: list[float] = []
    started = time.perf_counter()
    step = 0
    while step < settings.steps:
        for ids, weights in batches:
            if step >= settings.steps:
                break
            inputs = torch.tensor(ids, dtype=torch.long)
            weight = torch.tensor(weights, dtype=torch.float32)
            output = model(input_ids=inputs)
            logits = output.logits[:, :-1, :]
            targets = inputs[:, 1:]
            per_token = torch.nn.functional.cross_entropy(
                logits.reshape(-1, logits.shape[-1]), targets.reshape(-1), reduction="none"
            ).view(targets.shape)
            # FR-61: the weight of a decision multiplies its loss.
            per_sample = per_token.mean(dim=1)
            loss = (per_sample * weight).sum() / weight.sum()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.item()))
            step += 1
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(out / ADAPTER_FILE))
    record = {
        "profile": settings.to_dict(),
        "samples": len(chosen),
        "steps": step,
        "first_loss": round(losses[0], 4) if losses else 0.0,
        "last_loss": round(losses[-1], 4) if losses else 0.0,
        "finite_loss": all(math.isfinite(value) for value in losses),
        "seconds": round(time.perf_counter() - started, 2),
        "trainable_parameters": sum(p.numel() for p in trainable),
        "adapter": str(out / ADAPTER_FILE),
    }
    (out / MANIFEST_FILE).write_text(json.dumps(record, indent=1), encoding="utf-8")
    return record


def run_full(samples: Sequence[dict[str, Any]], out: Path, profile: Profile) -> dict[str, Any]:
    """The year-one run. It needs a GPU and the base model, so it waits for the owner."""
    raise FinetuneError(
        f"the full fine-tune of the profile {profile.name!r} runs on the owner's workstation with a "
        f"GPU and the base model {profile.base_model}. This build has the smoke run of TR-12 and the "
        "export of IR-08. Start the full run on that machine with `sl-cli finetune --full`."
    )
