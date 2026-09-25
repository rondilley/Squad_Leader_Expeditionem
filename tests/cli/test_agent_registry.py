"""The agent registry in `slagents.registry` (M1).

`make_agent` is a table of names and prefixes. The names it accepts and its error are the
ones of the if-chain in `slcli.play` before the move, and `slcli.play` and
`slcli.worker_limit` still give the same objects to their callers.
"""

from __future__ import annotations

import pytest

import slcli.play as play
import slcli.worker_limit as worker_limit
from slagents import registry
from slagents.base import RandomAgent
from slagents.scripted.v0 import ScriptedV0
from slagents.scripted.v1 import ScriptedV1
from slagents.scripted.v2 import ScriptedV2
from slagents.scripted.v3 import ScriptedV3
from slagents.scripted.v4 import ScriptedV4
from slagents.scripted.v5 import ScriptedV5
from slagents.scripted.v6 import ScriptedV6
from slagents.scripted.v7 import ScriptedV7

EXPECTED = {
    "random": RandomAgent,
    "v0": ScriptedV0,
    "v1": ScriptedV1,
    "v2": ScriptedV2,
    "v3": ScriptedV3,
    "v4": ScriptedV4,
    "v4:german": ScriptedV4,
    "v5": ScriptedV5,
    "v5:soviet": ScriptedV5,
    "v6": ScriptedV6,
    "v6:german": ScriptedV6,
    "v7": ScriptedV7,
    "v7:german": ScriptedV7,
    "v7[loss_scale=8]": ScriptedV7,
}


@pytest.fixture(scope="module")
def engine():
    return registry.build_engine("s01_guards_counterattack")


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_name_builds_its_agent(engine, name: str) -> None:
    agent = registry.make_agent(name, engine, 3, 1)
    assert type(agent) is EXPECTED[name]


def test_the_v7_parameters_come_from_the_brackets(engine) -> None:
    agent = registry.make_agent("v7[loss_scale=8]", engine, 3, 0)
    assert agent.v7.loss_scale == 8


@pytest.mark.parametrize("name", ["", "v8", "v7[loss_scale=8", "V1", "scripted", "v1:german"])
def test_an_unknown_name_gives_the_old_error(engine, name: str) -> None:
    with pytest.raises(ValueError) as caught:
        registry.make_agent(name, engine, 1, 0)
    assert str(caught.value) == (
        f"unknown agent kind {name!r}; use random, v0, v1, v2, v3, v4, v4:<nation>, v5, v5:<nation>, v6, v6:<nation>, v7, v7:<nation>, "
        "model:<providers>, tuned:<providers>, or learned:<snapshot>"
    )


def test_an_empty_snapshot_path_is_refused(engine) -> None:
    with pytest.raises(ValueError, match="snapshot path"):
        registry.make_agent("learned:", engine, 1, 0)


def test_an_empty_provider_list_is_refused(engine) -> None:
    with pytest.raises(ValueError, match="one provider name or more"):
        registry.make_agent("model:", engine, 1, 0)


def test_the_command_line_modules_give_the_same_objects() -> None:
    assert play.make_agent is registry.make_agent
    assert play.build_engine is registry.build_engine
    assert play.build_engine_with_record is registry.build_engine_with_record
    assert play.LearnedNotInstalled is registry.LearnedNotInstalled
    assert worker_limit.limit_workers is registry.limit_workers
    assert worker_limit.MAX_WORKERS == registry.MAX_WORKERS


def test_the_record_names_the_board(engine) -> None:
    built, record = registry.build_engine_with_record("s01_guards_counterattack")
    assert record["board"] == built.board.name
    assert built.hash_state(built.new_game(5)) == engine.hash_state(engine.new_game(5))
