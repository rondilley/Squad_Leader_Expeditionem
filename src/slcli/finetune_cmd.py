"""The fine-tune command (FR-61, TR-12, IR-08, TC-39).

`sl-cli finetune --data data/traces.jsonl --smoke` runs the fifty LoRA steps of TR-12 on
ten traces, which is the first of the three steps of the path. It needs no GPU and no
download, because the smoke model is built in memory.

`sl-cli finetune --data ... --full` runs the year-one profile. That needs the owner's
workstation, and this build says so instead of starting something it cannot finish.

`sl-cli finetune --export --adapter ...` merges the adapter and writes the GGUF file for
llama-server (IR-08).

The guard of SR-10 is on the data set and on this command. A data set with a record from a
reference-mode board is refused unless the owner gives `--local-only`, and the run artifact
of such a run says so.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from slagents.tuned import export as export_module
from slagents.tuned import finetune
from slcli.traces_cmd import GuardError, read_dataset
from slruns import artifact
from slruns.index import connect, upsert


def run(args: Any) -> int:
    data = Path(args.data)
    try:
        samples = read_dataset(data)
    except GuardError as exc:
        print(f"ERROR {exc}")
        return 2
    profile = finetune.SMOKE_PROFILE if args.smoke else finetune.Profile()
    if args.local_only:
        profile = finetune.Profile(**{**profile.to_dict(), "target_modules": tuple(profile.target_modules), "generated_traces_only": False})
    try:
        check = finetune.check_dataset(samples, profile, minimum_games=args.minimum_games)
    except finetune.FinetuneError as exc:
        print(f"ERROR {exc}")
        return 1
    print(f"{check['samples']} samples from {check['games']} games, weight total {check['weight_total']}")
    if not check["enough_games"]:
        print(
            f"WARNING the profile asks for {check['minimum_games']} games and the data set has "
            f"{check['games']}. The run goes on, and the artifact records the count."
        )
    out = Path(args.out)
    if args.export:
        return _export(args, out)
    art = artifact.RunArtifact(
        kind="finetune",
        slug=f"{profile.name}-lora",
        config={
            "scenario": "traces",
            "board": "generated",
            "data": str(data),
            "profile": profile.to_dict(),
            "dataset": check,
            "local_only": args.local_only,
            "criteria": ["TR-12", "FR-61", "NFR-09"],
        },
    )
    try:
        if args.smoke:
            record = finetune.run_smoke(samples, out, profile)
        else:
            record = finetune.run_full(samples, out, profile)
    except finetune.FinetuneError as exc:
        if isinstance(exc.__cause__, ImportError):
            # The extra is not installed: the typed exit code of a missing extra (B8).
            print(f"ERROR {exc}", file=sys.stderr)
            return 4
        print(f"ERROR {exc}")
        return 1
    art.stats = {**record, "passed": {"TR-12": bool(record.get("finite_loss")) and record.get("steps", 0) >= finetune.SMOKE_STEPS}}
    print(
        f"{record['steps']} steps on {record['samples']} samples in {record['seconds']} s, "
        f"loss {record['first_loss']} to {record['last_loss']}"
    )
    print(f"adapter {record['adapter']}")
    directory = art.write(args.runs)
    conn = connect(Path(args.runs) / "runs.sqlite")
    try:
        upsert(conn, directory)
    finally:
        conn.close()
    print(f"run artifact {directory}")
    return 0


def _export(args: Any, out: Path) -> int:
    adapter = Path(args.adapter) if args.adapter else out / finetune.ADAPTER_FILE
    result = export_module.run_export(adapter, args.base, out)
    print(json.dumps(result.to_dict(), indent=1))
    if result.gguf is None:
        print("the GGUF step did not run. The note above says what is missing (IR-08).")
        return 1
    try:
        answer = export_module.load_on_server(result.gguf.name)
    except export_module.ExportError as exc:
        print(f"the server step did not run: {exc}")
        return 1
    print(f"the local server answered with {answer['model']} in {answer['seconds']:.1f} s")
    return 0


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("finetune", help="fine-tune the tuned model agent on the trace data set")
    p.add_argument("--data", default="data/traces.jsonl", help="the data set from `sl-cli traces`")
    p.add_argument("--out", default="runs/finetune", help="directory for the adapter and the export")
    p.add_argument("--smoke", action="store_true", help="the fifty LoRA steps of TR-12")
    p.add_argument("--full", action="store_true", help="the year-one profile on the owner's workstation")
    p.add_argument("--export", action="store_true", help="merge the adapter and write the GGUF file (IR-08)")
    p.add_argument("--adapter", default=None, help="the adapter directory for the export")
    p.add_argument("--base", default=finetune.Profile().base_model, help="the base model of the merge")
    p.add_argument("--local-only", action="store_true", help="accept records from a reference-mode board (SR-10)")
    p.add_argument("--minimum-games", type=int, default=finetune.MINIMUM_GAMES)
    p.add_argument("--runs", default="runs")
    p.set_defaults(func=run)
