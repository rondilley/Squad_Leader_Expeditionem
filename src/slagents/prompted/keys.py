"""The key loader (SR-02, SR-01).

A key lives in `<provider>.key.txt` at the project root. `.gitignore` names those files on
its first line, so git never records one.

The rules of this module are short and each one is a requirement:

- The path resolves against the project root and nowhere else, so a provider name cannot
  read a file somewhere else on the machine.
- A line that starts with `#` is a comment. The first line that is not a comment and not
  empty is the key.
- When the file is absent, the environment variable takes its place.
- When neither is there, the provider is unavailable. That is a state, not an error: a
  run with four of five providers is a run.

Nothing here returns a key in a message, a log line, or an exception. A caller that wants
to know whether a key exists calls `available`, which gives a boolean.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SUFFIX = ".key.txt"
COMMENT = "#"
ENVIRONMENT = {
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "xai": "XAI_API_KEY",
}


class KeyMissing(Exception):
    """The provider has no key on this machine. The message never holds a key."""


@dataclass(frozen=True)
class KeySource:
    """Where a key came from. The value is not in this record."""

    provider: str
    kind: str  # "file", "environment", or "none"
    path: str = ""

    @property
    def found(self) -> bool:
        return self.kind != "none"


def project_root() -> Path:
    """The directory that holds the key files: the root of this repository."""
    return Path(__file__).resolve().parents[3]


def key_path(provider: str, root: Path | None = None) -> Path:
    """The path of one key file, checked to be a name and not a path."""
    if not provider or "/" in provider or "\\" in provider or provider.startswith("."):
        raise KeyMissing(f"the provider name {provider!r} is not a name")
    base = (root or project_root()).resolve()
    target = (base / f"{provider}{SUFFIX}").resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise KeyMissing(f"the provider name {provider!r} points outside the project root") from exc
    return target


def read_file(path: Path) -> str | None:
    """The first line that is not a comment and not empty."""
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError):
        return None
    except OSError:
        return None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(COMMENT):
            continue
        return stripped
    return None


def source_of(provider: str, root: Path | None = None) -> KeySource:
    """Where the key of this provider is, without reading its value into the answer."""
    try:
        path = key_path(provider, root)
    except KeyMissing:
        return KeySource(provider, "none")
    if read_file(path) is not None:
        return KeySource(provider, "file", str(path))
    name = ENVIRONMENT.get(provider, f"{provider.upper()}_API_KEY")
    if os.environ.get(name):
        return KeySource(provider, "environment", name)
    return KeySource(provider, "none")


def load(provider: str, root: Path | None = None) -> str:
    """The key of one provider. Raises KeyMissing, and the message holds no key."""
    source = source_of(provider, root)
    if source.kind == "file":
        value = read_file(Path(source.path))
        if value:
            return value
    if source.kind == "environment":
        value = os.environ.get(source.path)
        if value:
            return value
    raise KeyMissing(
        f"no key for the provider {provider!r}. Put it in {provider}{SUFFIX} at the project root, "
        f"or in the environment variable {ENVIRONMENT.get(provider, provider.upper() + '_API_KEY')}."
    )


def available(provider: str, root: Path | None = None) -> bool:
    """True when a key exists. This is the check a test skips on (TR-05)."""
    return source_of(provider, root).found


def redact(text: str, provider: str, root: Path | None = None) -> str:
    """Take a key out of a message before it reaches a log or an artifact (SR-01)."""
    try:
        key = load(provider, root)
    except KeyMissing:
        return text
    return text.replace(key, "[redacted]") if key else text
