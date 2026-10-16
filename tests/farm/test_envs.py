"""The PPO workers of the farm (`slfarm.envwire`, the env session of `slfarm.server`).

A remote worker is the loop of a local PPO worker on a farm host, and the trainer reads it
through a local pipe. The tests start a real server in this process and play real games:
a remote worker gives the decisions of a local worker with the same seed, a short training
run on the farm completes, and the host refuses a snapshot opponent, a bad command, and an
environment past its slots.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import threading
from pathlib import Path

import numpy as np
import pytest

from slagents.learned import ppo
from slagents.learned.nets import NetConfig
from slagents.learned.workers import WorkerDied, worker_main
from slcli.farm_cmd import scenario_names
from slcli.gauntlet import _play_job
from slcli.train import run_training
from slfarm import envwire
from slfarm import protocol as p
from slfarm.client import Address, Connection, Farm, RemoteEnvError, bridge, open_env
from slfarm.server import FarmServer, ServerThread

KEY = b"k" * 40
SCENARIO = "s01_guards_counterattack"
MAX_COMMANDS = 20_000


@pytest.fixture
def server():
    thread = ServerThread(FarmServer(KEY, _play_job, scenario_names(), slots=2, env_main=worker_main))
    host, port = thread.start()
    yield Address(host, port)
    thread.stop()


def _local_worker(seed: int):
    context = mp.get_context("spawn")
    ours, theirs = context.Pipe()
    process = context.Process(target=worker_main, args=(theirs, SCENARIO, 0, seed, MAX_COMMANDS), daemon=True)
    process.start()
    theirs.close()
    return ours, process


def _remote_worker(address: Address, seed: int):
    connection = open_env(address, KEY, SCENARIO, 0, seed, MAX_COMMANDS)
    ours, theirs = mp.Pipe()
    thread = threading.Thread(target=bridge, args=(theirs, connection), daemon=True)
    thread.start()
    return ours, thread


def _same(a, b) -> None:
    assert a.legal == b.legal
    assert a.reward_delta == b.reward_delta and a.ended == b.ended and a.result == b.result
    assert set(a.observation) == set(b.observation)
    for name in a.observation:
        assert a.observation[name].dtype == b.observation[name].dtype, name
        assert np.array_equal(a.observation[name], b.observation[name]), name


def test_a_remote_worker_gives_the_decisions_of_a_local_worker(server):
    local, process = _local_worker(77)
    remote, thread = _remote_worker(server, 77)
    try:
        for pipe in (local, remote):
            pipe.send(("reset", ("scripted", "v1"), 0, 1234, None))
        first_local, first_remote = local.recv(), remote.recv()
        _same(first_local, first_remote)
        for _ in range(6):
            key = first_local.legal[len(first_local.legal) // 2]
            local.send(("act", key))
            remote.send(("act", key))
            first_local, first_remote = local.recv(), remote.recv()
            _same(first_local, first_remote)
            if first_local.ended:
                break
    finally:
        for pipe in (local, remote):
            pipe.send(("stop",))
        process.join(10)
        thread.join(10)


def test_a_short_training_run_plays_on_the_farm(server, tmp_path: Path):
    art = run_training(
        scenario=SCENARIO,
        steps=128,
        hours=0.0,
        seed=6,
        learner_player=0,
        snapshot_every=0,
        config=ppo.PpoConfig(steps_per_update=64, minibatch=32, epochs=1),
        net=NetConfig(),
        out=tmp_path,
        log_dir=None,
        workers=1,
        opponents=["v1"],
        farm=Farm((server,), KEY),
        remote_envs=2,
    )
    assert art.stats["steps"] == 128 and art.stats["updates"] == 2
    assert art.config["remote_workers"] == 2 and art.config["farm"] == [str(server)]


STOP_AFTER = 20


def _relay_until_stop(connection, scenario: str, index: int, seed: int, max_commands: int, stops: bool) -> None:
    """The loop of a real PPO worker, in a thread. When `stops`, the process ends after
    `STOP_AFTER` commands with no answer, as a host or a network that fails."""
    inner, theirs = mp.Pipe()
    threading.Thread(target=worker_main, args=(theirs, scenario, index, seed, max_commands), daemon=True).start()
    count = 0
    while True:
        command = connection.recv()
        inner.send(command)
        if command[0] == "stop":
            return
        if stops and count == STOP_AFTER:
            os._exit(1)
        connection.send(inner.recv())
        count += 1


def _env_2_stops(connection, scenario: str, index: int, seed: int, max_commands: int) -> None:
    _relay_until_stop(connection, scenario, index, seed, max_commands, stops=index == 2)


def _each_env_stops(connection, scenario: str, index: int, seed: int, max_commands: int) -> None:
    _relay_until_stop(connection, scenario, index, seed, max_commands, stops=True)


def _train_on(env_main, out: Path):
    """One local worker (index 0) and two remote ones (indices 1 and 2)."""
    thread = ServerThread(FarmServer(KEY, _play_job, scenario_names(), slots=2, env_main=env_main))
    host, port = thread.start()
    try:
        return run_training(
            scenario=SCENARIO, steps=192, hours=0.0, seed=6, learner_player=0, snapshot_every=0,
            config=ppo.PpoConfig(steps_per_update=64, minibatch=32, epochs=1), net=NetConfig(),
            out=out, log_dir=None, workers=1, opponents=["v1"], farm=Farm((Address(host, port),), KEY), remote_envs=2,
        )
    finally:
        thread.stop()


def test_the_run_goes_on_when_a_remote_worker_stops(tmp_path: Path):
    """One bad line from one host stopped all 120 workers of a run (2026-10-16). Now the
    worker that stopped goes out of the pool, and the run completes with the others."""
    art = _train_on(_env_2_stops, tmp_path)
    assert art.stats["steps"] >= 192
    dropped = art.stats["dropped_workers"]
    assert [row["worker"] for row in dropped] == [2]
    assert "remote worker of the farm" in dropped[0]["error"]


def test_the_run_stops_when_fewer_than_half_of_its_workers_live(tmp_path: Path):
    """The pool starts with three workers. The loss of one leaves two, which is half or
    more. The loss of the second leaves one, which is less than half, so the run stops."""
    with pytest.raises(WorkerDied, match="remote worker of the farm"):
        _train_on(_each_env_stops, tmp_path)


def test_the_farm_needs_fixed_opponents(server, tmp_path: Path):
    with pytest.raises(ValueError, match="--opponents"):
        run_training(
            scenario=SCENARIO, steps=64, hours=0.0, seed=6, learner_player=0, snapshot_every=0,
            config=ppo.PpoConfig(steps_per_update=64, minibatch=32, epochs=1), net=NetConfig(),
            out=tmp_path, log_dir=None, farm=Farm((server,), KEY),
        )


def test_the_host_refuses_a_snapshot_opponent_and_a_bad_command(server):
    connection = open_env(server, KEY, SCENARIO, 0, 5, MAX_COMMANDS)
    try:
        connection.send({"type": "env", "command": ["reset", ["snapshot", "runs/x.pt"], 0, 1, None]})
        answer = connection.receive()
        assert answer["type"] == "env_error" and "scripted" in answer["error"]
    finally:
        connection.close()
    connection = open_env(server, KEY, SCENARIO, 0, 5, MAX_COMMANDS)
    try:
        connection.send({"type": "env", "command": ["act", [1, 2, "x", 4]]})
        with pytest.raises(p.FarmError):
            connection.receive()
    finally:
        connection.close()


def test_the_host_refuses_an_environment_past_its_slots(server):
    held = [open_env(server, KEY, SCENARIO, i, 5, MAX_COMMANDS) for i in range(2)]
    try:
        with pytest.raises(RemoteEnvError, match="slots"):
            open_env(server, KEY, SCENARIO, 2, 5, MAX_COMMANDS)
    finally:
        for connection in held:
            connection.close()


def test_a_host_with_no_train_extra_refuses_an_environment():
    thread = ServerThread(FarmServer(KEY, _play_job, scenario_names(), slots=1))
    host, port = thread.start()
    try:
        with pytest.raises(RemoteEnvError, match="train extra"):
            open_env(Address(host, port), KEY, SCENARIO, 0, 5, MAX_COMMANDS)
    finally:
        thread.stop()


def test_the_wire_checks_an_array_and_a_command():
    array = np.arange(12, dtype=np.float32).reshape(3, 4)
    assert np.array_equal(envwire.decode_array(envwire.encode_array(array)), array)
    bad = envwire.encode_array(array)
    bad["shape"] = [5, 4]
    with pytest.raises(p.FarmProtocolError):
        envwire.decode_array(bad)
    with pytest.raises(p.FarmProtocolError):
        envwire.decode_array({**envwire.encode_array(array), "dtype": "object"})
    assert envwire.check_command(["reset", ["scripted", "v7[mass=1]"], 1, 9, ["v7", 3]]) == ("reset", ("scripted", "v7[mass=1]"), 1, 9, ("v7", 3))
    assert envwire.check_command(envwire.encode_command(("act", (1, 2, 3, 4)))) == ("act", (1, 2, 3, 4))
    for command in (["reset", ["scripted", "learned:x.pt"], 0, 1, None], ["reset", ["random"], 0, 1, ["model:openai", 2]]):
        with pytest.raises(p.JobRefused):
            envwire.check_command(command)
    with pytest.raises(p.FarmProtocolError):
        envwire.check_command(["reset", ["random"], 2, 1, None])


def test_the_trainer_waits_on_more_pipes_than_one_windows_wait_takes():
    """The farm gives the trainer more than 63 workers, the limit of one wait on Windows."""
    pairs = [mp.Pipe() for _ in range(ppo.WAIT_LIMIT * 2 + 10)]
    ours = [pair[0] for pair in pairs]
    try:
        assert ppo.wait_any(ours, timeout=0.05) == []
        for index in (3, ppo.WAIT_LIMIT + 5, len(pairs) - 1):
            pairs[index][1].send("decision")
        assert set(ppo.wait_any(ours, timeout=None)) == {ours[3], ours[ppo.WAIT_LIMIT + 5], ours[-1]}
    finally:
        for a, b in pairs:
            a.close()
            b.close()


def test_a_bridge_process_says_why_a_host_did_not_open_its_environments(tmp_path: Path):
    thread = ServerThread(FarmServer(KEY, _play_job, scenario_names(), slots=1))
    host, port = thread.start()
    try:
        with pytest.raises(RemoteEnvError, match="train extra"):
            run_training(
                scenario=SCENARIO, steps=64, hours=0.0, seed=6, learner_player=0, snapshot_every=0,
                config=ppo.PpoConfig(steps_per_update=64, minibatch=32, epochs=1), net=NetConfig(),
                out=tmp_path, log_dir=None, workers=1, opponents=["v1"], farm=Farm((Address(host, port),), KEY),
            )
    finally:
        thread.stop()
