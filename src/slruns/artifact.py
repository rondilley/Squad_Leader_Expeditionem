"""The run artifact (DR-05, FR-56).

A run is a directory `runs/<ISO8601-Z>-<slug>/` with four files:

- `manifest.json`: what produced the run. Config, seeds, versions, and the hardware.
- `commands.json`: the command log, one entry for each command (DR-04).
- `log.json`: the action log, the events with their rule IDs (FR-06).
- `stats.json`: the derived numbers.

A run is self-contained: a future session reads it without the code that made it.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from slcore import __version__ as core_version

MANIFEST = "manifest.json"
COMMANDS = "commands.json"
LOG = "log.json"
STATS = "stats.json"
FILES = (MANIFEST, COMMANDS, LOG, STATS)

SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
# A slug longer than this is cut, and the cut carries a hash of the whole, because a
# Windows path has 260 characters and a v7 parameter text can be 300. The manifest
# holds the whole text.
SLUG_LIMIT = 72


class ArtifactError(Exception):
    """A run artifact could not be written or read."""


def slugify(text: str) -> str:
    out = SLUG_PATTERN.sub("-", text.lower()).strip("-")
    if len(out) > SLUG_LIMIT:
        digest = hashlib.sha256(out.encode("ascii")).hexdigest()[:8]
        out = out[: SLUG_LIMIT - 9].rstrip("-") + "-" + digest
    return out or "run"


def run_id(when: datetime, slug: str) -> str:
    stamp = when.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{slugify(slug)}"


def hardware() -> dict[str, Any]:
    import os

    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
    }


@dataclass
class RunArtifact:
    """One run on disk. Build it, add the parts, then write it."""

    kind: str
    slug: str
    config: dict[str, Any] = field(default_factory=dict)
    seeds: list[int] = field(default_factory=list)
    versions: dict[str, str] = field(default_factory=dict)
    commands: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    started: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def id(self) -> str:
        return run_id(self.started, self.slug)

    def manifest(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "slug": self.slug,
            "started": self.started.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "config": self.config,
            "seeds": self.seeds,
            "versions": {"slcore": core_version, **self.versions},
            "hardware": hardware(),
        }

    def write(self, root: str | Path = "runs") -> Path:
        directory = Path(root) / self.id
        try:
            directory.mkdir(parents=True, exist_ok=True)
            _write(directory / MANIFEST, self.manifest())
            _write(directory / COMMANDS, {"commands": self.commands})
            _write(directory / LOG, {"events": self.events})
            _write(directory / STATS, self.stats)
        except OSError as exc:
            raise ArtifactError(f"cannot write the run artifact in {directory}: {exc}") from exc
        return directory


def _write(path: Path, doc: Any) -> None:
    path.write_text(json.dumps(doc, indent=1, sort_keys=False), encoding="utf-8")


def read(directory: str | Path) -> dict[str, Any]:
    """The four files of a run as one dictionary."""
    d = Path(directory)
    out: dict[str, Any] = {}
    for name in FILES:
        path = d / name
        try:
            out[name.removesuffix(".json")] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ArtifactError(f"the run at {d} has no {name}") from exc
        except OSError as exc:
            raise ArtifactError(f"cannot read {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ArtifactError(f"{path} is not valid JSON: {exc}") from exc
    return out


def complete(directory: str | Path) -> bool:
    d = Path(directory)
    return all((d / name).is_file() for name in FILES)


def find_runs(root: str | Path = "runs") -> Iterable[Path]:
    r = Path(root)
    if not r.is_dir():
        return []
    return sorted(p for p in r.iterdir() if p.is_dir() and complete(p))
