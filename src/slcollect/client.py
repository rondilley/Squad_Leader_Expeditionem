"""The uploader of the packaged game: it sends each saved game that a person played.

`send_pending` reads the save directory, and for each game with a decision of a person that
the collector does not have in full, it sends the file. `sent.json` in the data directory
holds the count of lines that the collector has of each game, so a game that the player
resumed goes again with its new lines. A network error leaves the game for the next try:
the launcher tries at its start and after each game.

The uploader never stops the game. Each error is a line of the report.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from slcollect import wire
from slcollect.keys import PlayerKey
from slcollect.verify import human_count
from slhost.savegame import SaveFileError, load

TIMEOUT_SECONDS = 20.0
# A save file that changed in the last seconds can be a game in play.
QUIET_SECONDS = 30.0


@dataclass
class UploadReport:
    sent: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    stopped: str = ""

    def text(self) -> str:
        parts = [f"{len(self.sent)} games sent"]
        if self.already:
            parts.append(f"{len(self.already)} the collector had")
        if self.refused:
            parts.append(f"{len(self.refused)} refused")
        if self.errors:
            parts.append(f"{len(self.errors)} to send again later")
        if self.stopped:
            parts.append(f"stopped: {self.stopped}")
        return ", ".join(parts)


def _read_sent(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_sent(path: Path, sent: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(sent, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def post(url: str, key: PlayerKey, body: bytes, timeout: float = TIMEOUT_SECONDS) -> tuple[int, dict[str, Any]]:
    """One signed POST. Gives the status and the answer; a network error is an `OSError`."""
    request = urllib.request.Request(
        url.rstrip("/") + wire.PATH_GAMES, data=body, method="POST", headers=wire.signed_headers(key.name, key.secret, body)
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, text = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, text = exc.code, exc.read()
    try:
        answer = json.loads(text.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        answer = {"error": f"the collector gave a body that is not JSON (status {status})"}
    return status, answer if isinstance(answer, dict) else {"error": "the answer is not an object"}


def send_pending(
    save_dir: Path,
    url: str,
    key: PlayerKey,
    sent_file: Path,
    package: str,
    quiet_seconds: float = QUIET_SECONDS,
    now: float | None = None,
) -> UploadReport:
    """Send each game of `save_dir` with a decision of a person that the collector does not have."""
    report = UploadReport()
    now = time.time() if now is None else now
    sent = _read_sent(sent_file)
    for path in sorted(Path(save_dir).glob("*.jsonl")):
        try:
            if now - path.stat().st_mtime < quiet_seconds:
                continue
            header, lines = load(path)
        except (OSError, SaveFileError):
            continue
        game_id = str(header["game_id"])
        record = sent.get(game_id, {})
        if isinstance(record, dict) and record.get("lines") == len(lines):
            continue
        if human_count(lines) == 0:
            continue
        body = wire.encode_upload([header, *lines], package)
        if len(body) > wire.MAX_BODY:
            report.refused.append(f"{game_id}: larger than the collector takes")
            sent[game_id] = {"lines": len(lines), "status": "too large"}
            continue
        try:
            status, answer = post(url, key, body)
        except OSError as exc:
            report.errors.append(f"{game_id}: {exc}")
            report.stopped = f"the collector at {url} did not answer"
            break
        if status == 200:
            (report.sent if answer.get("stored") else report.already).append(game_id)
            sent[game_id] = {"lines": len(lines), "status": "verified" if answer.get("verified") else "kept, not verified"}
        elif status in (409, 413, 422):
            report.refused.append(f"{game_id}: {answer.get('error', status)}")
            sent[game_id] = {"lines": len(lines), "status": f"refused: {answer.get('error', status)}"}
        elif status == 401:
            report.stopped = f"the collector refused the key: {answer.get('error', '')}"
            break
        else:
            report.errors.append(f"{game_id}: status {status} {answer.get('error', '')}")
            if status == 429:
                break
    _write_sent(sent_file, sent)
    return report
