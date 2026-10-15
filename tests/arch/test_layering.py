"""The import layers of `src/` (M1, AR-01, AR-06).

The test reads each module of `src/` with `ast` and makes the graph of the absolute
imports, the late imports in a function too. Three rules:

1. `slcore` imports only `slcore` and the standard library. The core has no file, no
   network, and no third party library, so the Rust port has one surface to copy.
2. The library packages (`slagents`, `slshape`, `slboards`, `sldata`, `slruns`, `slfarm`) do not
   import `slcli` or `slhost`. The command line and the host are consumers.
3. `slhost` does not import `slcli`.

`ALLOWED_FOR_NOW` holds an edge that is known and has an owner. The test fails on a new
edge, and it fails too when an allowed edge is gone, so the set gets smaller.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"

LIBRARIES = ("slagents", "slshape", "slboards", "sldata", "slruns", "slfarm")
CONSUMERS = ("slcli", "slhost")

# (file below src, imported module). Each one has a cause and the change that removes it.
ALLOWED_FOR_NOW: frozenset[tuple[str, str]] = frozenset()


def packages() -> set[str]:
    return {p.name for p in SRC.iterdir() if p.is_dir() and (p / "__init__.py").exists()}


def imports_of(path: Path) -> list[str]:
    """Each absolute module name that the file imports, at the top or in a function."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    return names


def edges() -> list[tuple[str, str, str]]:
    """(file below src, top package of the file, imported module) for each import."""
    out: list[tuple[str, str, str]] = []
    for package in sorted(packages()):
        for path in sorted((SRC / package).rglob("*.py")):
            rel = path.relative_to(SRC).as_posix()
            for module in imports_of(path):
                out.append((rel, package, module))
    return out


def violations() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    for rel, package, module in edges():
        top = module.split(".")[0]
        if package == "slcore":
            if top != "slcore" and top not in stdlib:
                found.add((rel, module))
        elif package in LIBRARIES:
            if top in CONSUMERS:
                found.add((rel, module))
        elif package == "slhost":
            if top == "slcli":
                found.add((rel, module))
    return found


def test_the_graph_reads_each_package() -> None:
    # A test of the reader: the graph holds edges that are known to be there.
    known = {(rel, module) for rel, _, module in edges()}
    assert ("slcli/play.py", "slagents.registry") in known
    assert {"slcore", "slagents", "slcli", "slhost"} <= packages()


def test_no_new_import_crosses_a_layer() -> None:
    new = sorted(violations() - ALLOWED_FOR_NOW)
    assert not new, "imports that cross a layer:\n" + "\n".join(f"{rel} imports {module}" for rel, module in new)


def test_each_allowed_edge_is_still_there() -> None:
    gone = sorted(ALLOWED_FOR_NOW - violations())
    assert not gone, "remove these from ALLOWED_FOR_NOW:\n" + "\n".join(f"{rel} imports {module}" for rel, module in gone)


def test_the_reader_finds_a_crossing(tmp_path: Path) -> None:
    # The same reader on a file with a late import of slcli gives the edge.
    sample = tmp_path / "sample.py"
    sample.write_text("def f():\n    from slcli.play import make_agent\n    return make_agent\n", encoding="utf-8")
    assert imports_of(sample) == ["slcli.play"]
