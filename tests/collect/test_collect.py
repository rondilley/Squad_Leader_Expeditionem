"""The collection of played games (`slcollect`): the keys, the wire, the replay check, the
collector on a local port, and the uploader of the packaged game.

Each game is a real host game with a save file. The person's commands are the commands of a
scripted agent applied with the source `human`, which is what the host records for a click.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from slagents.base import decide
from slagents.registry import build_engine, make_agent
from slcollect import keys as keystore
from slcollect import settings as player_settings
from slcollect import wire
from slcollect.client import post, send_pending
from slcollect.server import make_server, scenario_names
from slcollect.verify import GameRejected, Verifier
from slhost.savegame import load
from slhost.server import SOURCE_HUMAN, Host

SCENARIO = "s01_guards_counterattack"


def _play(save_dir: Path, commands: int, human_player: int | None = 0, seed: int = 3) -> Path:
    """A host game of `commands` commands; the commands of `human_player` have the source human."""
    engine = build_engine(SCENARIO)
    host = Host(engine, seed=seed, save_dir=save_dir)
    game = host.game
    agents = (make_agent("v1", engine, seed, 0), make_agent("v1", engine, seed, 1))
    for _ in range(commands):
        if game.state.game_over:
            break
        frame = engine.legal_commands(game.state)
        source = SOURCE_HUMAN if frame.player == human_player else "computer"
        game.apply(frame.frame_id, decide(agents[frame.player], game.state, frame), source)
    return game.save.path


def _go_on(path: Path, commands: int, seed: int = 3) -> None:
    """More commands in the same save file, as a resumed game gives."""
    engine = build_engine(SCENARIO)
    host = Host(engine, seed=seed)
    host.resume_from(path)
    game = host.game
    agents = (make_agent("v1", engine, seed, 0), make_agent("v1", engine, seed, 1))
    for _ in range(commands):
        frame = engine.legal_commands(game.state)
        game.apply(frame.frame_id, decide(agents[frame.player], game.state, frame), SOURCE_HUMAN if frame.player == 0 else "computer")


@pytest.fixture(scope="module")
def played(tmp_path_factory) -> Path:
    return _play(tmp_path_factory.mktemp("saves"), 80)


@pytest.fixture()
def collector(tmp_path):
    store = tmp_path / "collect_keys.key.txt"
    key = keystore.add_key(store, "player-one")
    logs: list[str] = []
    server = make_server(tmp_path / "data", store, "127.0.0.1", 0, log=logs.append)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    yield url, key, store, tmp_path / "data", logs
    server.shutdown()
    server.server_close()


def test_a_key_file_reads_back_and_a_revoked_key_has_no_secret(tmp_path):
    store = tmp_path / "keys.key.txt"
    key = keystore.add_key(store, "ann")
    path = keystore.write_player_file(tmp_path / "collect.key.txt", key)
    assert keystore.read_player_file(path) == key
    assert keystore.active_secret(keystore.load_store(store), "ann") == key.secret
    keystore.revoke_key(store, "ann")
    assert keystore.active_secret(keystore.load_store(store), "ann") is None
    with pytest.raises(keystore.KeyStoreError):
        keystore.add_key(store, "Bad Name")
    with pytest.raises(keystore.KeyStoreError):
        keystore.add_key(store, "ann")


def test_the_mac_covers_each_byte_of_the_body():
    secret = b"k" * 32
    headers = wire.signed_headers("ann", secret, b'{"a":1}', now=1000)
    stamp, nonce = headers[wire.HEADER_TIME], headers[wire.HEADER_NONCE]
    assert wire.mac_of(secret, "POST", wire.PATH_GAMES, stamp, nonce, b'{"a":1}') == headers[wire.HEADER_MAC]
    assert wire.mac_of(secret, "POST", wire.PATH_GAMES, stamp, nonce, b'{"a":2}') != headers[wire.HEADER_MAC]
    with pytest.raises(wire.WireError):
        wire.decode_upload(b'{"package": "1", "game": []}')


def test_the_replay_verifies_a_game_and_finds_a_changed_hash(played):
    verifier = Verifier(scenario_names())
    header, lines = load(played)
    good = verifier.check([header, *lines])
    assert good.verified and good.commands == len(lines) and good.human_commands > 0
    changed = [dict(line) for line in lines]
    changed[10]["hash"] = "0" * len(changed[10]["hash"])
    bad = verifier.check([header, *changed])
    assert not bad.verified and "command 10" in bad.reason
    with pytest.raises(GameRejected, match="no decision of a person"):
        verifier.check([header, *[{**line, "source": "computer"} for line in lines]])
    with pytest.raises(GameRejected, match="not a scenario"):
        verifier.check([{**header, "scenario": "no_such_scenario"}, *lines])


def test_the_uploader_sends_a_game_once_and_again_when_it_grows(collector, tmp_path):
    url, key, _store, data, _logs = collector
    saves = tmp_path / "saves"
    path = _play(saves, 60)
    sent_file = tmp_path / "sent.json"
    first = send_pending(saves, url, key, sent_file, "test", quiet_seconds=0)
    assert first.sent == [load(path)[0]["game_id"]] and not first.errors, first.text()
    kept = data / "games" / path.name
    assert kept.read_text(encoding="utf-8") == path.read_text(encoding="utf-8")
    index = [json.loads(line) for line in (data / "index.jsonl").read_text(encoding="utf-8").splitlines()]
    assert index[0]["key"] == "player-one" and index[0]["verified"] is True
    again = send_pending(saves, url, key, sent_file, "test", quiet_seconds=0)
    assert again.sent == [] and again.already == [], "the record of the sent games stops a second send"
    _go_on(path, 20)
    grown = send_pending(saves, url, key, sent_file, "test", quiet_seconds=0)
    assert grown.sent == [load(path)[0]["game_id"]], grown.text()
    assert kept.read_text(encoding="utf-8") == path.read_text(encoding="utf-8"), "the collector keeps the longer game"


def test_a_game_of_computers_only_is_not_sent(collector, tmp_path):
    url, key, _store, data, _logs = collector
    saves = tmp_path / "saves"
    _play(saves, 30, human_player=None)
    report = send_pending(saves, url, key, tmp_path / "sent.json", "test", quiet_seconds=0)
    assert report.sent == [] and report.refused == [] and not list((data / "games").iterdir())


def test_the_collector_refuses_a_false_key_a_revoked_key_and_a_second_send(collector, played, tmp_path):
    url, key, store, _data, _logs = collector
    header, lines = load(played)
    body = wire.encode_upload([header, *lines], "test")
    false_key = keystore.PlayerKey("player-one", b"x" * 32)
    assert post(url, false_key, body)[0] == 401
    unknown = keystore.PlayerKey("nobody", key.secret)
    assert post(url, unknown, body)[0] == 401
    import urllib.request

    headers = wire.signed_headers(key.name, key.secret, body)
    request = urllib.request.Request(url + wire.PATH_GAMES, data=body, method="POST", headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        assert response.status == 200
    import urllib.error

    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(urllib.request.Request(url + wire.PATH_GAMES, data=body, method="POST", headers=headers), timeout=30)
    assert caught.value.code == 401 and b"nonce" in caught.value.read()
    old = wire.signed_headers(key.name, key.secret, body, now=1_000_000)
    with pytest.raises(urllib.error.HTTPError) as stale:
        urllib.request.urlopen(urllib.request.Request(url + wire.PATH_GAMES, data=body, method="POST", headers=old), timeout=30)
    assert stale.value.code == 401
    keystore.revoke_key(store, "player-one")
    report = send_pending(played.parent, url, key, tmp_path / "sent.json", "test", quiet_seconds=0)
    assert "refused the key" in report.stopped


def test_the_uploader_keeps_a_game_when_the_collector_does_not_answer(played, tmp_path):
    key = keystore.PlayerKey("player-one", b"k" * 32)
    sent_file = tmp_path / "sent.json"
    report = send_pending(played.parent, "http://127.0.0.1:9", key, sent_file, "test", quiet_seconds=0)
    assert report.errors and "did not answer" in report.stopped
    assert json.loads(sent_file.read_text(encoding="utf-8")) == {}, "the game goes again at the next try"


def test_the_settings_keep_the_consent_and_name_the_collector(tmp_path, monkeypatch):
    monkeypatch.setenv("SL_DATA_DIR", str(tmp_path / "player"))
    monkeypatch.delenv("SL_COLLECTOR", raising=False)
    first = player_settings.load_settings()
    assert first.consent is None, "the first start asks"
    first.set_consent(True)
    assert player_settings.load_settings().consent is True
    assert player_settings.collector_url(first) == player_settings.DEFAULT_COLLECTOR
    first.collector = "http://example.invalid:1/"
    assert player_settings.collector_url(first) == "http://example.invalid:1"
    monkeypatch.setenv("SL_COLLECTOR", "http://other.invalid:2")
    assert player_settings.collector_url(first) == "http://other.invalid:2"
    assert player_settings.key_file() is None
    keystore.write_player_file(player_settings.data_dir() / keystore.PLAYER_FILE, keystore.PlayerKey("ann", b"s" * 32))
    assert player_settings.key_file() == player_settings.data_dir() / keystore.PLAYER_FILE
