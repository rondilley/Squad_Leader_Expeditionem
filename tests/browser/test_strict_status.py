"""The host tells the client whether line of sight is strict. The client shows the text.

The client does not send a mode, and the page has no checkbox for one (AR-06).
"""

from __future__ import annotations

from pathlib import Path

from slhost import protocol

ROOT = Path(__file__).resolve().parents[2]
STRICT = "strict line of sight: the host answers a line of sight question only in a fire phase (rule 19.3)"
OPEN = "line of sight: the host answers a line of sight question in any phase"


def test_the_welcome_carries_the_host_flag():
    message = protocol.welcome(0, "hot_seat", {"name": "board"}, {"id": "s"}, strict_los=True)
    assert message["strict_los"] is True
    casual = protocol.welcome(1, "german", {"name": "board"}, {"id": "s"})
    assert casual["strict_los"] is False


def test_the_client_shows_the_host_flag_and_has_no_checkbox():
    page = (ROOT / "client" / "index.html").read_text(encoding="utf-8")
    source = (ROOT / "client" / "src" / "main.ts").read_text(encoding="utf-8")
    assert 'id="strict"' not in page
    assert "strictBox" not in source
    assert STRICT in source
    assert OPEN in source
    assert "message.strict_los" in source
