"""The ceiling on a worker count.

A command that starts one process for each worker has no other limit. A large count
forks until the machine stops. 64 is enough for the benches and the gauntlets on the
owner's machines, and it refuses a larger count at the command line and at each pool.
"""

from __future__ import annotations

import argparse

MAX_WORKERS = 64


def limit_workers(workers: int) -> int:
    """The count, when it is from 1 to `MAX_WORKERS`."""
    if workers < 1 or workers > MAX_WORKERS:
        raise ValueError(f"workers must be from 1 to {MAX_WORKERS}, not {workers}")
    return workers


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
