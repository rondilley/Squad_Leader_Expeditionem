"""sl-cli entry point."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from slcli import (
    agents_cmd,
    bench,
    boards_cmd,
    campaign_cmd,
    cards_cmd,
    collect_cmd,
    launch_cmd,
    evolve,
    farm_cmd,
    gates,
    gauntlet,
    host_cmd,
    library_cmd,
    play,
    runs_cmd,
    shape_cmd,
    tournament,
    traces_cmd,
    window_cmd,
    window3d_cmd,
)

# The libraries of the optional extras. A missing one of these removes a command and puts
# a command in its place that names the extra (B8). A missing module of this project, or
# of the base install, is a defect, and the import error goes up.
TRAIN_LIBRARIES = frozenset({"torch", "numpy", "pettingzoo", "gymnasium", "tensorboard"})
FINETUNE_LIBRARIES = frozenset({"torch", "transformers", "peft", "datasets", "accelerate"})


# The extra that gives each optional library, for the message of a late import (B8).
EXTRA_OF_LIBRARY = {
    "torch": "train",
    "numpy": "train",
    "pettingzoo": "train",
    "gymnasium": "train",
    "tensorboard": "train",
    "transformers": "finetune",
    "peft": "finetune",
    "datasets": "finetune",
    "accelerate": "finetune",
    "pygame": "desktop",
    "panda3d": "view3d",
    "playwright": "browser",
}


def _missing_optional(exc: ModuleNotFoundError, libraries: frozenset[str]) -> bool:
    return (exc.name or "").split(".")[0] in libraries


try:  # the trainer needs the `train` extra, and the other commands do not
    from slcli import imitate_cmd
    from slcli import train as train_cmd
except ModuleNotFoundError as _exc:
    if not _missing_optional(_exc, TRAIN_LIBRARIES):
        raise
    train_cmd = None
    imitate_cmd = None

try:  # the fine-tune needs the `finetune` extra
    from slcli import finetune_cmd
except ModuleNotFoundError as _exc:
    if not _missing_optional(_exc, FINETUNE_LIBRARIES):
        raise
    finetune_cmd = None
from slcli.cards_cmd import CardsNotInstalled
from slcli.play import LearnedNotInstalled
from slcli.shape_cmd import ShapeNotInstalled
from slcli.window_cmd import DesktopNotInstalled
from slcli.window3d_cmd import View3DNotInstalled
from slfarm.protocol import FarmError
from slruns.artifact import ArtifactError
from slruns.index import IndexError_
from sldata.loaders import DataError
from slcampaign.generator import ScenarioError


class ExtraNotInstalled(Exception):
    """A command needs an optional extra that is not installed."""

    def __init__(self, command: str, extra: str, libraries: str) -> None:
        super().__init__(
            f"the {command} command needs {libraries}. Install it with: pip install -e \".[{extra}]\""
        )


def _add_missing(sub: Any, command: str, extra: str, libraries: str) -> None:
    """A command whose extra is not installed. It takes any argument and gives the typed error."""

    def refuse(_args: Any) -> int:
        raise ExtraNotInstalled(command, extra, libraries)

    p = sub.add_parser(command, help=f"(needs the {extra} extra: {libraries})")
    p.add_argument("rest", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    p.set_defaults(func=refuse)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sl-cli", description="Play, host, measure, and compare with the rules core.")
    sub = parser.add_subparsers(dest="command", required=True)
    play.add_parser(sub)
    bench.add_parser(sub)
    tournament.add_parser(sub)
    gates.add_parser(sub)
    gauntlet.add_parser(sub)
    evolve.add_parser(sub)
    farm_cmd.add_parser(sub)
    collect_cmd.add_parser(sub)
    launch_cmd.add_parser(sub)
    shape_cmd.add_parser(sub)
    host_cmd.add_parser(sub)
    runs_cmd.add_parser(sub)
    boards_cmd.add_parser(sub)
    cards_cmd.add_parser(sub)
    agents_cmd.add_parser(sub)
    traces_cmd.add_parser(sub)
    campaign_cmd.add_parser(sub)
    library_cmd.add_parser(sub)
    window_cmd.add_parser(sub)
    window3d_cmd.add_parser(sub)
    if train_cmd is not None:
        train_cmd.add_parser(sub)
        imitate_cmd.add_parser(sub)
    else:
        _add_missing(sub, "train", "train", "torch and numpy")
        _add_missing(sub, "imitate", "train", "torch and numpy")
    if finetune_cmd is not None:
        finetune_cmd.add_parser(sub)
    else:
        _add_missing(sub, "finetune", "finetune", "torch, transformers, and peft")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, rest = parser.parse_known_args(argv)
    if rest and getattr(args, "rest", None) is None:
        parser.error(f"unrecognized arguments: {' '.join(rest)}")
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
    except View3DNotInstalled as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 4
    except (ShapeNotInstalled, LearnedNotInstalled, CardsNotInstalled, ExtraNotInstalled) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 4
    except ModuleNotFoundError as exc:
        # A late import of an optional library that no typed error covers. A missing
        # module of this project is a defect, and it goes up with its trace.
        library = (exc.name or "").split(".")[0]
        extra = EXTRA_OF_LIBRARY.get(library)
        if extra is None:
            raise
        print(f"ERROR the {args.command} command needs {library}. Install it with: pip install -e \".[{extra}]\"", file=sys.stderr)
        return 4
    except FarmError as exc:
        print(f"ERROR farm: {exc}", file=sys.stderr)
        return 5
    except (RuntimeError, ValueError, NotImplementedError, ScenarioError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
