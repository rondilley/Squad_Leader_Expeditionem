"""The questions of the window client stay below the request limit of the host (SR-03).

A fast sweep of the pointer asks a line of sight for each hex, and each frame asks the
options of the unit in focus. Before 2026-10-26 a burst of more than 30 questions in 5
seconds got the code `rate_limited`, which the client read as a refused join: it showed
"the host refused too many join tries" and stopped the session.
"""

from __future__ import annotations

import time

from slcli.play import build_engine
from slhost import protocol
from slhost.server import Host
from slwindow import client as client_module
from slwindow.client import QUESTION_LIMIT, HostClient
from slwindow.embedded import start

from tests.window.test_window_play_v2 import wait_for


def test_a_burst_of_questions_keeps_the_session_and_the_rest_goes_later(monkeypatch):
    host = Host(build_engine("lib01_grain_office"), seed=1)
    embedded = start(host)
    client = HostClient(embedded.url, embedded.room_code, "test window")
    client.start()
    try:
        wait_for(client, lambda s: bool(s.frame_id))
        sent = [client.request_los("A1", f"B{i % 9 + 1}") for i in range(QUESTION_LIMIT + 11)]
        assert sent.count(True) == QUESTION_LIMIT, "the client keeps below the limit of the host"
        assert not any(sent[QUESTION_LIMIT:])
        assert client.request_options(10) is False, "the options share the budget"
        time.sleep(1.0)
        snapshot = client.snapshot()
        assert snapshot.error_code == "" and client._terminal is None
        # After the window of time the questions go again.
        later = time.monotonic() + client_module.QUESTION_WINDOW_SECONDS + 0.1
        monkeypatch.setattr(client_module.time, "monotonic", lambda: later)
        assert client.request_options(10) is True
    finally:
        client.stop()
        embedded.stop()


def test_the_question_limit_of_the_host_does_not_end_the_session():
    client = HostClient("ws://127.0.0.1:1", "ROOM", "test window")
    client._receive({"type": "error", "rule_id": "SR-03", "message": "wait a few seconds", "code": protocol.CODE_REQUEST_LIMITED})
    assert client._terminal is None
    assert client.snapshot().notice.startswith("the window asked the host too many questions")
    client._receive({"type": "error", "rule_id": "SR-03", "message": "join", "code": protocol.CODE_RATE_LIMITED})
    assert client._terminal is not None, "a refused join still ends the session"
