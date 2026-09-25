"""The breaker counts only the failures a rest can cure, and a message holds no key (L6).

Each test runs a real HTTP server on the loopback address and a real adapter against it,
so the status code, the error, and the redaction are the ones a real call gives.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from slagents.prompted import keys
from slagents.prompted.providers import ProviderError, ProviderUnavailable
from slagents.prompted.providers.base import ProviderConfig, is_transient
from slagents.prompted.providers.gemini import GeminiProvider
from slagents.prompted.providers.openai_compatible import OpenAiCompatibleProvider
from slagents.prompted.router import Router

GOOD = b'{"choices": [{"message": {"content": "{\\"command_id\\": \\"abc\\"}"}, "finish_reason": "stop"}]}'


@contextmanager
def server(status: int, body: bytes = b'{"error": "no"}', echo_header: str | None = None):
    """A server that answers each POST with `status`. With `echo_header` the body is that header's value."""
    calls: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.path)
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            payload = body
            if echo_header is not None:
                payload = ("the request had the key " + str(self.headers.get(echo_header, ""))).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt, *args):
            return

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}", calls
    finally:
        httpd.shutdown()
        httpd.server_close()


def adapter(name: str, origin: str) -> OpenAiCompatibleProvider:
    row = ProviderConfig(name=name, kind="openai_compatible", endpoint=origin + "/v1", model="m", timeout_seconds=5.0)
    return OpenAiCompatibleProvider(row, (origin,))


def test_a_deterministic_400_moves_the_call_on_and_opens_no_breaker():
    """A 400 comes back on each call, so a rest cures nothing. Before the correction two
    of them took the host out of the sequence, one host of a pool after the other."""
    with server(400) as (bad_origin, bad_calls), server(200, GOOD) as (good_origin, _):
        router = Router([adapter("first", bad_origin), adapter("second", good_origin)], failures_to_open=2, rest_seconds=300.0)
        for _ in range(3):
            assert router.complete("s", "u").provider == "second"
        assert len(bad_calls) == 3, "the provider that refused the request stays in the sequence"
        assert router.breakers["first"].failures == 0
        rows = router.report()["failovers"]
        assert all(row["status"] == 400 and row["counted"] is False and not row["breaker_open"] for row in rows)


@pytest.mark.parametrize("status", [408, 429, 500, 503])
def test_a_busy_answer_opens_the_breaker(status: int):
    with server(status) as (bad_origin, bad_calls), server(200, GOOD) as (good_origin, _):
        router = Router([adapter("first", bad_origin), adapter("second", good_origin)], failures_to_open=2, rest_seconds=300.0)
        for _ in range(3):
            assert router.complete("s", "u").provider == "second"
        assert len(bad_calls) == 2, f"two answers of {status} took the provider out for its rest"
        assert router.report()["failovers"][0]["counted"] is True


def test_a_host_that_does_not_answer_is_transient():
    """A closed port is a network error, which a rest can cure."""
    probe = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    origin = f"http://127.0.0.1:{probe.server_address[1]}"
    probe.server_close()
    with pytest.raises(ProviderUnavailable) as exc:
        adapter("gone", origin).complete("s", "u")
    assert is_transient(exc.value)
    assert not is_transient(ProviderError("a refused request", status=404))


def test_the_redaction_uses_the_key_name_the_adapter_loads(tmp_path: Path, monkeypatch):
    """A Gemini row with no key name loads the `gemini` key. A server that puts the key
    in its error body gives a message with no key, because the redaction reads the same
    name. The key is a value of this test, in a key root of its own."""
    secret = "sk-test-gemini-value-0001"
    (tmp_path / "gemini.key.txt").write_text(secret + "\n", encoding="utf-8")
    monkeypatch.setattr(keys, "project_root", lambda: tmp_path)
    with server(400, echo_header="x-goog-api-key") as (origin, calls):
        row = ProviderConfig(name="g", kind="gemini", endpoint=origin + "/v1beta", model="m", timeout_seconds=5.0)
        provider = GeminiProvider(row, (origin,))
        assert provider.key_name() == "gemini"
        with pytest.raises(ProviderError) as exc:
            provider.complete("s", "u")
    assert len(calls) == 1 and exc.value.status == 400
    message = str(exc.value)
    leaked = secret in message
    assert not leaked, "the error message holds the key"
    assert "[redacted]" in message
