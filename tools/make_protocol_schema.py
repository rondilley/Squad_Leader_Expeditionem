"""Write the shared protocol schema from `slhost.protocol` (Slice 9 item 5).

`src/slhost/protocol.py` is the one source of the message names, the error codes, the
terminal codes, the statuses, the controllers, the seat names, and the field names of
each message. This tool writes two files from `protocol.schema()`:

- `src/slhost/protocol_schema.json`: the schema as JSON, for a reader in any language.
- `client/src/net/protocol_schema.ts`: the same document as a TypeScript constant with
  `as const`. The client imports it. TypeScript gives a JSON import the type `string`
  for each value, and the tagged union of the host messages needs the literal types, so
  the client reads a module and not the JSON file.

Run it after a change to `protocol.py`:

    python tools/make_protocol_schema.py

`--check` writes nothing. It gives exit code 1 when a file is not current.
`tests/arch/test_protocol_schema.py` does the same comparison.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slhost import protocol  # noqa: E402

JSON_PATH = ROOT / "src" / "slhost" / "protocol_schema.json"
TS_PATH = ROOT / "client" / "src" / "net" / "protocol_schema.ts"

TS_HEADER = """// GENERATED FILE. Do not edit. tools/make_protocol_schema.py writes it from
// src/slhost/protocol.py, which is the one source of the protocol names (Slice 9 item 5).
// Run `python tools/make_protocol_schema.py` after a change to the protocol.

"""


def json_text() -> str:
    return json.dumps(protocol.schema(), indent=2, sort_keys=False) + "\n"


def ts_text() -> str:
    body = json.dumps(protocol.schema(), indent=2, sort_keys=False)
    return TS_HEADER + f"export const SCHEMA = {body} as const;\n"


def rendered() -> dict[Path, str]:
    """The text of each generated file, keyed by its path.

    A checkout with no client tree (git does not record `client/` yet, finding B2) gets
    the JSON file only, so the tool does not make a part of a client.
    """
    files = {JSON_PATH: json_text()}
    if (ROOT / "client" / "package.json").is_file():
        files[TS_PATH] = ts_text()
    return files


def stale(files: dict[Path, str]) -> list[Path]:
    """The generated files that are missing or different from `files`."""
    out = []
    for path, text in files.items():
        try:
            current = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            out.append(path)
            continue
        if current != text:
            out.append(path)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if a file is not current")
    args = parser.parse_args(argv)
    files = rendered()
    if args.check:
        old = stale(files)
        for path in old:
            print(f"ERROR: {path.relative_to(ROOT)} is not current; run python tools/make_protocol_schema.py")
        return 1 if old else 0
    for path, text in files.items():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except OSError as exc:
            print(f"ERROR: cannot write {path}: {exc}", file=sys.stderr)
            return 2
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
