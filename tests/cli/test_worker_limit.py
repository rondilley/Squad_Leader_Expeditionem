"""The worker count has a ceiling."""

from __future__ import annotations

import argparse

import pytest

from slcli.worker_limit import MAX_WORKERS, limit_workers, worker_list_argument, workers_argument


def test_a_worker_count_above_the_ceiling_is_refused():
    assert limit_workers(1) == 1
    assert limit_workers(MAX_WORKERS) == MAX_WORKERS
    with pytest.raises(ValueError) as exc:
        limit_workers(MAX_WORKERS + 1)
    assert str(MAX_WORKERS) in str(exc.value)
    with pytest.raises(argparse.ArgumentTypeError):
        workers_argument(str(MAX_WORKERS + 1))
    with pytest.raises(argparse.ArgumentTypeError):
        worker_list_argument(f"1,{MAX_WORKERS + 1}")
    assert worker_list_argument("1,8,16") == "1,8,16"
