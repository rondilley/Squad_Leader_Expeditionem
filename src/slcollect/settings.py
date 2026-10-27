"""The player's data directory, the consent, the collector address, and the key file.

The data directory holds the saved games, `settings.json`, the record of the sent games,
and the key file of the player:

    Windows: %LOCALAPPDATA%\\SquadLeaderExpeditionem
    Linux:   $XDG_DATA_HOME/squad-leader-expeditionem (~/.local/share/squad-leader-expeditionem)

`SL_DATA_DIR` changes it, for the tests and for a second player on one computer.

The consent is asked one time, at the first start (`consent` None). The answer is True or
False, and the player can change it in the launcher. With False or None the game sends
nothing; it saves each game on the disk in all cases.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from slcollect.keys import PLAYER_FILE

# The collector of the first tests (owner, 2026-10-27). The package can name another one in
# `collector.json` next to the program, and `SL_COLLECTOR` changes it for one run.
DEFAULT_COLLECTOR = "http://tars.uberadmin.com:5170"
APP_NAME_WINDOWS = "SquadLeaderExpeditionem"
APP_NAME_UNIX = "squad-leader-expeditionem"


def data_dir() -> Path:
    override = os.environ.get("SL_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME_WINDOWS
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME_UNIX


def app_dir() -> Path | None:
    """The folder of the packaged program, or None when the game runs from the source tree."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


def games_dir() -> Path:
    return data_dir() / "games"


def package_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("squad_leader_ai")
    except Exception:  # noqa: BLE001 - a frozen program can have no metadata
        return "unknown"


@dataclass
class Settings:
    consent: bool | None = None
    consent_at: str = ""
    collector: str = ""
    player_name: str = ""

    @property
    def path(self) -> Path:
        return data_dir() / "settings.json"

    def to_dict(self) -> dict[str, Any]:
        return {"consent": self.consent, "consent_at": self.consent_at, "collector": self.collector, "player_name": self.player_name}

    def save(self) -> None:
        target = self.path
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(json.dumps(self.to_dict(), indent=1, sort_keys=True), encoding="utf-8")
        os.replace(temporary, target)

    def set_consent(self, value: bool) -> None:
        self.consent = bool(value)
        self.consent_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.save()


def load_settings() -> Settings:
    """The settings of the player. A file that is missing or broken gives the first start."""
    path = data_dir() / "settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Settings()
    if not isinstance(data, dict):
        return Settings()
    consent = data.get("consent")
    return Settings(
        consent=consent if isinstance(consent, bool) else None,
        consent_at=str(data.get("consent_at") or ""),
        collector=str(data.get("collector") or ""),
        player_name=str(data.get("player_name") or ""),
    )


def collector_url(settings: Settings | None = None) -> str:
    """The address of the collector: `SL_COLLECTOR`, the settings, `collector.json`, the default."""
    override = os.environ.get("SL_COLLECTOR")
    if override:
        return override.rstrip("/")
    if settings is not None and settings.collector:
        return settings.collector.rstrip("/")
    folder = app_dir()
    if folder is not None:
        try:
            data = json.loads((folder / "collector.json").read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("url"), str) and data["url"]:
                return data["url"].rstrip("/")
        except (OSError, json.JSONDecodeError):
            pass
    return DEFAULT_COLLECTOR


def key_file() -> Path | None:
    """The key file of the player: in the data directory, or next to the program."""
    candidates = [data_dir() / PLAYER_FILE]
    folder = app_dir()
    if folder is not None:
        candidates.append(folder / PLAYER_FILE)
    for path in candidates:
        if path.is_file():
            return path
    return None
