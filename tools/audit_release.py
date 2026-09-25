"""The release audit (SR-01, SR-06, SR-07, SR-08, TC-25, TC-28, TC-29).

One command answers the question the owner asks before a release: does this tree, and does
the page it serves, hold anything that must not leave this machine?

The audit reads the source tree, the built client, the fixtures, the screenshots, and the
run artifacts. It gives one line for each finding and an exit code of 1 when it finds one.

What it looks for:

- A key file, in the tree or in the git history (TC-25, SR-01).
- A scan or a photograph: an image or a PDF outside `background/`, which git does not
  record (TC-29, SR-07). The one exception is `docs/images/`, and only for a file that
  `docs/images/MANIFEST.json` names. `tools/make_docs_images.py` writes those files and
  that manifest, and `tests/docs/test_documentation_images.py` makes each picture again
  and compares it, so a scan that a person puts there does not pass.
- Rulebook text or card text: a block quote that follows a line naming a rule of the 4th
  edition or a section of a scenario card (TC-29, SR-07).
- A board layout transcribed from the four printed boards: a board data file named after
  one of them (TC-29, FR-27).
- The licence notice and the source link on the served page (TC-28, SR-06).
- The brand as the name of the page (SR-08).

The audit does not read `background/`. That directory is the owner's reference material,
git does not record it, and its content is the reason the audit exists.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PRIVATE_DIRECTORY = "background"
# The one directory that may hold an image, and only a picture that the project made from
# its own code. `tools/make_docs_images.py` writes the pictures and the manifest.
PICTURE_DIRECTORY = ("docs", "images")
PICTURE_MANIFEST = "MANIFEST.json"
KEY_SUFFIX = ".key.txt"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".pdf", ".psd"}
SKIP_DIRECTORIES = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
TEXT_SUFFIXES = {".md", ".txt", ".json", ".py", ".ts", ".html", ".css", ".yaml", ".yml"}

RULE_TAG = re.compile(r"\[RULES-4E\]|\bRules? \d+\.\d+\b.*:\s*$")
CARD_SECTION = re.compile(
    r"^\s*[-*]?\s*(Victory Conditions|Special Rules|Variations|Aftermath|Card text|Force list|Order of Battle)\s*:?\s*$",
    re.I,
)
FENCE = re.compile(r"^\s*```")
BLOCK_QUOTE = re.compile(r"^\s*>")
PRINTED_BOARDS = re.compile(r"^board[1-4]\.json$", re.I)
LICENCE_MARKERS = ("GPL-3", "GNU General Public License")
SOURCE_MARKERS = ("Corresponding Source", "source code", "source:")
BRAND_WORDS = ("Squad Leader", "Avalon Hill")
NON_AFFILIATION = "not affiliated"
# The owner named the public title on 2026-09-18. It is the one title that may hold a brand
# word, and the page must still carry the non-affiliation notice (SR-08).
PUBLIC_TITLE = "Squad Leader Expeditionem"


@dataclass(frozen=True)
class Finding:
    """One thing the audit found."""

    criterion: str
    path: str
    line: int
    detail: str

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"{self.criterion} {where}: {self.detail}"

    def to_dict(self) -> dict[str, Any]:
        return {"criterion": self.criterion, "path": self.path, "line": self.line, "detail": self.detail}


def walk(root: Path) -> Iterable[Path]:
    """Each file of the tree, without the private directory and the build directories."""
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        parts = set(path.relative_to(root).parts)
        if parts & SKIP_DIRECTORIES:
            continue
        if path.relative_to(root).parts and path.relative_to(root).parts[0] == PRIVATE_DIRECTORY:
            continue
        yield path


def key_pattern_ignored(root: Path) -> bool:
    """Whether `.gitignore` names the key files, which is where SR-01 puts them."""
    ignore = root / ".gitignore"
    if not ignore.is_file():
        return False
    for line in ignore.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip() in (f"*{KEY_SUFFIX}", KEY_SUFFIX.lstrip(".")):
            return True
    return False


def check_keys(root: Path) -> list[Finding]:
    """TC-25 and SR-01: a key file that git records, or that `.gitignore` does not name.

    A key file at the project root is where SR-01 puts it, so a file on this machine is not
    a finding. A file that git records is a finding, and so is a tree whose `.gitignore`
    does not name the pattern, because the next key file there would be recorded.
    """
    found: list[Finding] = []
    if not key_pattern_ignored(root):
        for path in walk(root):
            if path.name.endswith(KEY_SUFFIX):
                found.append(
                    Finding("TC-25", str(path.relative_to(root)), 0, "a key file is in the tree and .gitignore does not name it")
                )
    try:
        result = subprocess.run(
            ["git", "log", "--all", "--name-only", "--pretty=format:"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return found + [Finding("TC-25", ".", 0, f"cannot read the git history: {exc}")]
    names: set[str] = set()
    if result.returncode == 0:
        names.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    if tracked.returncode == 0:
        # A force-added key is in the index before it is in the history.
        names.update(part for part in tracked.stdout.split("\0") if part)
    for name in sorted(names):
        if name.endswith(KEY_SUFFIX):
            found.append(Finding("TC-25", name, 0, "a key file is in the git history or the index"))
    return found


def named_pictures(root: Path) -> set[str]:
    """The file names that `docs/images/MANIFEST.json` gives, or none when it is not there."""
    manifest = root.joinpath(*PICTURE_DIRECTORY, PICTURE_MANIFEST)
    if not manifest.is_file():
        return set()
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    return {str(image.get("file", "")) for image in document.get("images", [])}


def check_images(root: Path) -> list[Finding]:
    """TC-29 and SR-07: a scan or a photograph outside the private directory.

    A picture that the project makes from its own code is not a scan. Those live in
    `docs/images/`, and the manifest there names each one. An image in that directory that
    the manifest does not name is a finding, because that is how a scan would arrive.
    """
    found: list[Finding] = []
    allowed = named_pictures(root)
    for path in walk(root):
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if relative.parts[:-1] == PICTURE_DIRECTORY:
            if relative.name in allowed:
                continue
            found.append(
                Finding(
                    "TC-29",
                    str(relative),
                    0,
                    f"an image in {'/'.join(PICTURE_DIRECTORY)}/ that {PICTURE_MANIFEST} does not name",
                )
            )
            continue
        found.append(
            Finding("TC-29", str(relative), 0, f"an image or a document outside {PRIVATE_DIRECTORY}/")
        )
    for name in sorted(allowed):
        if not root.joinpath(*PICTURE_DIRECTORY, name).is_file():
            found.append(
                Finding(
                    "TC-29",
                    "/".join(PICTURE_DIRECTORY) + "/" + PICTURE_MANIFEST,
                    0,
                    f"the manifest names {name}, and that file is not there",
                )
            )
    return found


def check_quotes(root: Path) -> list[Finding]:
    """TC-29 and SR-07: a block quote of the rulebook or of a scenario card."""
    found: list[Finding] = []
    for path in walk(root):
        if path.suffix.lower() != ".md":
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
        for i, line in enumerate(lines):
            if FENCE.match(line):
                context = _quote_context(lines, i, skip_quote=False)
                if RULE_TAG.search(context) or CARD_SECTION.match(context):
                    found.append(
                        Finding(
                            "TC-29",
                            str(path.relative_to(root)),
                            i + 1,
                            f"a block quote follows {context.strip()[:60]!r}",
                        )
                    )
                continue
            if not BLOCK_QUOTE.match(line):
                continue
            context = _quote_context(lines, i, skip_quote=True)
            if RULE_TAG.search(context) or CARD_SECTION.match(context):
                found.append(
                    Finding(
                        "TC-29",
                        str(path.relative_to(root)),
                        i + 1,
                        f"a block quote follows {context.strip()[:60]!r}",
                    )
                )
    return found


def _quote_context(lines: list[str], index: int, skip_quote: bool) -> str:
    """The nearest earlier line that is not empty, and not another quote line when asked."""
    for back in range(1, 6):
        if index - back < 0:
            break
        earlier = lines[index - back]
        if not earlier.strip():
            continue
        if skip_quote and BLOCK_QUOTE.match(earlier):
            continue
        return earlier
    return ""


def check_boards(root: Path) -> list[Finding]:
    """TC-29 and FR-27: a layout of one of the four printed boards in the tree."""
    found: list[Finding] = []
    for path in walk(root):
        if PRINTED_BOARDS.match(path.name):
            found.append(
                Finding("TC-29", str(path.relative_to(root)), 0, "a board data file named after a printed board")
            )
    return found


def check_page(root: Path, page: Path | None) -> list[Finding]:
    """TC-28, SR-06, and SR-08: the notice, the source link, and the name of the page."""
    found: list[Finding] = []
    candidates = [page] if page else [root / "client" / "dist" / "index.html", root / "client" / "index.html"]
    target = next((p for p in candidates if p and p.is_file()), None)
    if target is None:
        return [Finding("TC-28", "client/dist/index.html", 0, "there is no built page to audit")]
    text = target.read_text(encoding="utf-8", errors="replace")
    where = str(target.relative_to(root))
    if not any(marker in text for marker in LICENCE_MARKERS):
        found.append(Finding("TC-28", where, 0, "the page has no GPL-3 notice"))
    if not any(marker in text for marker in SOURCE_MARKERS):
        found.append(Finding("TC-28", where, 0, "the page has no link to the source"))
    title = re.search(r"<title>(.*?)</title>", text, re.S)
    if title and title.group(1).strip() != PUBLIC_TITLE:
        for word in BRAND_WORDS:
            if word.lower() in title.group(1).lower():
                found.append(Finding("SR-08", where, 0, f"the title of the page uses {word!r} as the name"))
    if any(word.lower() in text.lower() for word in BRAND_WORDS) and NON_AFFILIATION not in text.lower():
        found.append(Finding("SR-08", where, 0, "the page names the brand and has no non-affiliation notice"))
    return found


def check_artifacts(root: Path, runs: Path) -> list[Finding]:
    """SR-10: a public run artifact that came from a reference-mode board."""
    found: list[Finding] = []
    if not runs.is_dir():
        return found
    paths = sorted(runs.rglob("*.json")) + sorted(runs.rglob("*.jsonl"))
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if path.suffix == ".json":
            try:
                text = json.dumps(json.loads(text))
            except json.JSONDecodeError:
                continue
        if "reference_private" in text:
            found.append(
                Finding("SR-10", str(path.relative_to(root)), 0, "a run artifact holds a reference-mode record")
            )
    return found


def audit(root: Path, runs: Path, page: Path | None) -> list[Finding]:
    return (
        check_keys(root)
        + check_images(root)
        + check_quotes(root)
        + check_boards(root)
        + check_page(root, page)
        + check_artifacts(root, runs)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The release audit of SR-07 and SR-08.")
    parser.add_argument("--root", default=".", help="the tree to audit")
    parser.add_argument("--runs", default="runs", help="the run directory")
    parser.add_argument("--page", default=None, help="the built page, when it is not in client/dist")
    parser.add_argument("--json", action="store_true", help="write the findings as JSON")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    findings = audit(root, Path(args.runs) if Path(args.runs).is_absolute() else root / args.runs, Path(args.page) if args.page else None)
    if args.json:
        print(json.dumps([f.to_dict() for f in findings], indent=1))
    else:
        for finding in findings:
            print(finding)
        print(f"{len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
