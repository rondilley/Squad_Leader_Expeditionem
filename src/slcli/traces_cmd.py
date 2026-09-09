"""The traces command: build the training data set from the runs (FR-60, SR-10, TC-39).

`sl-cli traces --from runs --out data/traces.jsonl` reads each trace file under a
directory, applies the guard of SR-10, and writes one JSON object for each decision in the
format the fine-tune reads.

The guard is the point of this command. A trace from a game on a reference-mode board
carries `board_source = "reference_private"`. The default build refuses the whole data set
when it finds one, and it names the file. The owner can pass `--local-only` to accept them,
and then the data set and anything trained on it stay on the owner's machine (SR-10).

The importance weight of a record comes from what the decision was. A fire decision and a
rout decision change the game more than an end-phase decision, and the Diplomacy report
names that weight as its largest quality increase (RV-8 section 4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from slagents.tuned import traces
from slagents.tuned.traces import TraceError, TraceRecord

DEFAULT_OUT = Path("data") / "traces.jsonl"
TRACE_GLOB = "traces*.json"

# The weight of one decision in the loss (FR-61). A decision that ends a phase is one that
# the rules often force, and a decision that fires or routs is one the player thought about.
WEIGHTS = {
    "group_fire": 3.0,
    "ft_fire": 3.0,
    "explode_demo": 3.0,
    "cc_attack": 3.0,
    "rout": 2.5,
    "group_add": 2.0,
    "group_add_weapon": 2.0,
    "group_leader": 2.0,
    "place_demo": 2.0,
    "place_smoke": 2.0,
    "sewer_move": 2.0,
    "move": 1.5,
    "stack_move": 1.5,
    "advance": 1.5,
    "rally": 1.5,
    "place": 1.0,
    "place_weapon": 1.0,
    "place_concealment": 1.0,
    "end_phase": 0.5,
    "end_setup": 0.5,
}
DEFAULT_WEIGHT = 1.0


class GuardError(Exception):
    """The data set holds a record that the default build refuses (SR-10)."""


@dataclass(frozen=True)
class Sample:
    """One line of the data set: the prompt, the answer, and the weight."""

    prompt: str
    answer: str
    weight: float
    game_id: str
    decision: int
    action: str
    family: str
    result: str
    board_source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "answer": self.answer,
            "weight": self.weight,
            "game_id": self.game_id,
            "decision": self.decision,
            "action": self.action,
            "family": self.family,
            "result": self.result,
            "board_source": self.board_source,
        }


def find_files(root: Path) -> list[Path]:
    """Each trace file under a directory, in a stable sequence."""
    return sorted(p for p in root.rglob(TRACE_GLOB) if p.is_file())


def weight_of(record: TraceRecord) -> float:
    action = str(record.selected_payload.get("action", ""))
    return WEIGHTS.get(action, DEFAULT_WEIGHT)


def prompt_of(record: TraceRecord) -> str:
    """The text the model reads: the view and the legal identities."""
    lines = [record.view_text, "", "Legal commands:"]
    lines.extend(f"  {identity}" for identity in record.legal_command_ids)
    lines.append("")
    lines.append("Answer with one of the identities above.")
    return "\n".join(lines)


def sample_of(record: TraceRecord) -> Sample:
    return Sample(
        prompt=prompt_of(record),
        answer=record.selected_command_id,
        weight=weight_of(record),
        game_id=record.game_id,
        decision=record.decision,
        action=str(record.selected_payload.get("action", "")),
        family=record.family,
        result=record.result,
        board_source=record.board_source,
    )


def build(root: Path, local_only: bool = False) -> tuple[list[Sample], dict[str, Any]]:
    """The data set and its record. Raises GuardError on a private trace (SR-10, TC-39)."""
    files = find_files(root)
    samples: list[Sample] = []
    private_files: list[str] = []
    games: set[str] = set()
    families: dict[str, int] = {}
    for path in files:
        try:
            records = traces.read(path)
        except TraceError as exc:
            raise GuardError(f"cannot read the trace file {path}: {exc}") from exc
        private = traces.private_count(records)
        if private and not local_only:
            private_files.append(f"{path} ({private} records)")
            continue
        for record in records:
            samples.append(sample_of(record))
            games.add(record.game_id)
            families[record.family] = families.get(record.family, 0) + 1
    if private_files and not local_only:
        raise GuardError(
            "the trace set holds records from a reference-mode board, and the default build "
            f"refuses them (SR-10): {'; '.join(private_files)}. Use --local-only to accept them, "
            "and then the data set and anything trained on it stay on this machine."
        )
    record = {
        "files": len(files),
        "games": len(games),
        "samples": len(samples),
        "families": families,
        "local_only": local_only,
        "private_records": sum(1 for s in samples if s.board_source == traces.SOURCE_REFERENCE),
        "weight_total": round(sum(s.weight for s in samples), 2),
    }
    return samples, record


def write(samples: Iterable[Sample], path: Path) -> int:
    """One JSON object for each line, which is what the fine-tune reads."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample.to_dict(), sort_keys=True) + "\n")
            count += 1
    return count


def read_dataset(path: Path) -> list[dict[str, Any]]:
    """The data set back from disk."""
    out: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    except FileNotFoundError as exc:
        raise GuardError(f"there is no data set at {path}") from exc
    except json.JSONDecodeError as exc:
        raise GuardError(f"{path} holds a line that is not JSON: {exc}") from exc
    return out


def run(args: Any) -> int:
    root = Path(args.source)
    if not root.is_dir():
        print(f"ERROR there is no directory {root}")
        return 2
    try:
        samples, record = build(root, args.local_only)
    except GuardError as exc:
        print(f"ERROR {exc}")
        return 1
    out = Path(args.out)
    count = write(samples, out)
    print(f"{count} samples from {record['games']} games in {record['files']} files")
    print(f"families {record['families']}")
    if record["local_only"]:
        print("this data set was built with --local-only, so it stays on this machine (SR-10)")
    print(f"data set {out}")
    return 0


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("traces", help="build the training data set from the trace files (FR-60)")
    p.add_argument("--source", default="runs", help="the directory to read the trace files from")
    p.add_argument("--out", default=str(DEFAULT_OUT), help="the data set file to write")
    p.add_argument(
        "--local-only",
        action="store_true",
        help="accept traces from a reference-mode board. The data set then stays on this machine (SR-10).",
    )
    p.set_defaults(func=run)
