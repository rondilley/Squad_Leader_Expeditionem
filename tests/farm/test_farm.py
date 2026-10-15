"""The game farm (`slfarm`): a server that plays games for an authenticated client.

The tests start a real server on the loopback address in this process and play real games
of the drill scenario on it. The gauntlet with the farm must give the artifact of the
gauntlet on one machine (TR-02), a wrong key and other code are refused, a job that is not
a scripted game is refused, and the games of a host that fails go to another slot.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from slcli.farm_cmd import scenario_names
from slcli.gauntlet import _play_job, run_gauntlet
from slfarm import protocol as p
from slfarm.client import Address, Connection, Farm, parse_addresses, ping, play_all
from slfarm.server import FarmServer, ServerThread

KEY = b"k" * 40
SCENARIO = "s00_movement_drill"


@pytest.fixture
def server():
    thread = ServerThread(FarmServer(KEY, _play_job, scenario_names(), slots=2))
    host, port = thread.start()
    yield Address(host, port)
    thread.stop()


def test_the_gauntlet_on_the_farm_gives_the_artifact_of_one_machine(server):
    alone = run_gauntlet(candidate="v1", panel=["random", "v0"], scenarios=[SCENARIO], games=4, seed=11)
    farmed = run_gauntlet(
        candidate="v1", panel=["random", "v0"], scenarios=[SCENARIO], games=4, seed=11, farm=Farm((server,), KEY)
    )
    assert farmed.seeds == alone.seeds
    assert farmed.stats["pairs"] == alone.stats["pairs"]
    assert farmed.stats["leaderboard"] == alone.stats["leaderboard"]
    assert farmed.config["farm"] == [str(server)]


def test_play_all_returns_the_results_in_the_order_of_the_jobs(server):
    jobs = [(SCENARIO, seed, "v1", "v0") for seed in range(20, 26)]
    local = [_play_job(job) for job in jobs]
    assert play_all(jobs, [server], KEY) == local
    # Two connections to the one host and one local worker share the list.
    assert play_all(jobs, [server, server], KEY, local_workers=1, play=_play_job) == local


def test_a_wrong_key_is_refused(server):
    with pytest.raises(p.FarmAuthError):
        Connection(server, b"x" * 40, p.code_hash())


def test_a_host_with_other_code_is_refused():
    thread = ServerThread(FarmServer(KEY, _play_job, scenario_names(), slots=1, code="0" * 64))
    host, port = thread.start()
    try:
        with pytest.raises(p.FarmVersionError):
            Connection(Address(host, port), KEY, p.code_hash())
    finally:
        thread.stop()


def test_the_server_refuses_a_job_that_is_not_a_scripted_game(server):
    connection = Connection(server, KEY, p.code_hash())
    try:
        for job in (
            {"type": "job", "id": 1, "scenario": SCENARIO, "seed": 1, "agents": ["learned:runs/x.pt", "v1"]},
            {"type": "job", "id": 2, "scenario": SCENARIO, "seed": 1, "agents": ["model:openai", "v1"]},
            {"type": "job", "id": 3, "scenario": "../../etc/passwd", "seed": 1, "agents": ["v1", "v1"]},
            {"type": "job", "id": 4, "scenario": SCENARIO, "seed": -1, "agents": ["v1", "v1"]},
            {"type": "job", "id": 5, "scenario": "s99_none", "seed": 1, "agents": ["v1", "v1"]},
        ):
            connection.send(job)
            answer = connection.receive()
            assert answer["type"] == "refused" and answer["id"] == job["id"], answer
        assert connection.ping()["type"] == "pong", "the connection stays open after a refusal"
    finally:
        connection.close()


def test_the_client_refuses_a_learned_or_model_agent_before_it_sends(server):
    with pytest.raises(p.JobRefused):
        play_all([(SCENARIO, 1, "learned:runs/x.pt", "v1")], [server], KEY)


def test_a_line_that_is_not_json_closes_the_connection(server):
    connection = Connection(server, KEY, p.code_hash())
    try:
        connection.sock.sendall(b"this is not json\n")
        with pytest.raises(p.FarmError):
            connection.receive()
    finally:
        connection.close()


def _dead_host() -> tuple[socket.socket, Address]:
    """A host that sends a valid challenge and accepts the key, takes one job, and closes."""
    import threading

    listener = socket.create_server(("127.0.0.1", 0))
    host, port = listener.getsockname()[:2]

    def run() -> None:
        conn, _ = listener.accept()
        f = conn.makefile("rb")
        nonce = p.new_nonce()
        conn.sendall(p.encode({"type": "challenge", "protocol": p.PROTOCOL, "nonce": nonce, "code": p.code_hash(), "slots": 3}))
        f.readline()
        conn.sendall(p.encode({"type": "ready"}))
        f.readline()
        # The file of makefile holds the socket open, so it closes first.
        f.close()
        conn.close()

    threading.Thread(target=run, daemon=True).start()
    return listener, Address(host, port)


def test_the_games_of_a_host_that_fails_go_to_another_slot(server):
    jobs = [(SCENARIO, seed, "v1", "v0") for seed in range(30, 36)]
    local = [_play_job(job) for job in jobs]
    listener, dead = _dead_host()
    try:
        assert play_all(jobs, [dead, server], KEY, result_timeout=60) == local
    finally:
        listener.close()


def test_a_run_with_no_host_left_stops_with_an_error():
    listener, dead = _dead_host()
    try:
        with pytest.raises(p.FarmError):
            play_all([(SCENARIO, 1, "v1", "v0")], [dead], KEY, result_timeout=60)
    finally:
        listener.close()


def test_ping_names_each_host_and_the_key_file_rules(server, tmp_path: Path):
    rows = ping([server, Address("127.0.0.1", 1)], KEY)
    assert rows[0]["slots"] == 2 and rows[0]["busy"] == 0
    assert "error" in rows[1]
    short = tmp_path / "short.key.txt"
    short.write_text("abc\n", encoding="utf-8")
    with pytest.raises(p.FarmKeyError):
        p.read_key(short)
    with pytest.raises(p.FarmKeyError):
        p.read_key(tmp_path / "missing.key.txt")
    good = tmp_path / "good.key.txt"
    good.write_text(p.new_key() + "\n", encoding="utf-8")
    assert len(p.read_key(good)) == 64
    assert parse_addresses("tars,case:5170") == [Address("tars", p.DEFAULT_PORT), Address("case", 5170)]
    with pytest.raises(ValueError):
        parse_addresses("tars:http")


def test_the_code_hash_reads_crlf_and_lf_the_same(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    for root, end in ((a, "\n"), (b, "\r\n")):
        (root / "pkg").mkdir(parents=True)
        (root / "pkg" / "m.py").write_bytes(f"x = 1{end}y = 2{end}".encode())
        (root / "pkg" / "__pycache__").mkdir()
        (root / "pkg" / "__pycache__" / "m.json").write_text("{}", encoding="utf-8")
    assert p.code_hash(a) == p.code_hash(b)
    (b / "pkg" / "m.py").write_bytes(b"x = 2\n")
    assert p.code_hash(a) != p.code_hash(b)


def test_a_scenario_file_of_the_workstation_plays_on_the_farm(server, tmp_path: Path):
    """A variant under test is a file on the workstation and not a scenario of the host,
    so the job carries its document, and the host gives the result of one machine."""
    import json

    from slcli.play import build_engine

    document = json.loads((Path(__file__).resolve().parents[2] / "src" / "sldata" / "scenarios" / f"{SCENARIO}.json").read_text(encoding="utf-8"))
    document["turns"] = int(document["turns"]) + 1
    variant = tmp_path / "variant.json"
    variant.write_text(json.dumps(document), encoding="utf-8")
    name = f"file:{variant}"
    assert build_engine(name).scenario.turns == document["turns"]
    jobs = [(name, seed, "v1", "v0") for seed in range(40, 44)]
    assert play_all(jobs, [server], KEY) == [_play_job(job) for job in jobs]


def test_the_server_refuses_a_scenario_document_that_is_not_valid(server):
    connection = Connection(server, KEY, p.code_hash())
    try:
        for job_id, document in enumerate(([1, 2], {"id": "x"}, "s00_movement_drill")):
            connection.send({"type": "job", "id": job_id, "scenario_doc": document, "seed": 1, "agents": ["v1", "v1"]})
            answer = connection.receive()
            assert answer["type"] == "refused" and answer["id"] == job_id, answer
    finally:
        connection.close()
