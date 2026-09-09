"""sl-cli entry point."""

from __future__ import annotations

import argparse
import sys

from slcli import (
    agents_cmd,
    bench,
    boards_cmd,
    campaign_cmd,
    gates,
    host_cmd,
    play,
    runs_cmd,
    tournament,
    traces_cmd,
    window_cmd,
)

try:  # the trainer needs the `train` extra, and the other commands do not
    from slcli import train as train_cmd
except ImportError:  # pragma: no cover - exercised on a machine with no torch
    train_cmd = None

try:  # the fine-tune needs the `finetune` extra
    from slcli import finetune_cmd
except ImportError:  # pragma: no cover - exercised on a machine with no transformers
    finetune_cmd = None
from slcli.window_cmd import DesktopNotInstalled
from slruns.artifact import ArtifactError
from slruns.index import IndexError_
from sldata.loaders import DataError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sl-cli", description="Play, host, measure, and compare with the rules core.")
    sub = parser.add_subparsers(dest="command", required=True)
    play.add_parser(sub)
    bench.add_parser(sub)
    tournament.add_parser(sub)
    gates.add_parser(sub)
    host_cmd.add_parser(sub)
    runs_cmd.add_parser(sub)
    boards_cmd.add_parser(sub)
    agents_cmd.add_parser(sub)
    traces_cmd.add_parser(sub)
    campaign_cmd.add_parser(sub)
    window_cmd.add_parser(sub)
    if train_cmd is not None:
        train_cmd.add_parser(sub)
    if finetune_cmd is not None:
        finetune_cmd.add_parser(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except DataError as exc:
        print(f"ERROR data: {exc}", file=sys.stderr)
        return 2
    except (ArtifactError, IndexError_) as exc:
        print(f"ERROR run artifact: {exc}", file=sys.stderr)
        return 3
    except DesktopNotInstalled as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 4
    except (RuntimeError, ValueError, NotImplementedError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
