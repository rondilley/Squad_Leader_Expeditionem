"""The ceiling on a worker count, as argparse types.

The ceiling and `limit_workers` are in `slagents.registry`, because each pool of the
library reads them. This module gives the command line types that refuse a count
outside the ceiling.
"""

from __future__ import annotations

import argparse

from slagents.registry import MAX_WORKERS, limit_workers  # noqa: F401  re-exported for the callers of slcli.worker_limit


def workers_argument(text: str) -> int:
    """The argparse type for one worker count."""
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"workers must be an integer, not {text!r}") from exc
    try:
        return limit_workers(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def worker_list_argument(text: str) -> str:
    """The argparse type for a bench list such as `1,8,16`."""
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("workers needs one count or more")
    for part in parts:
        workers_argument(part)
    return text
