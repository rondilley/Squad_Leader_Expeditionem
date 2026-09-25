"""The public surface of the core in `slcore.api` (M4, AR-05).

Two checks. One: each name in `api.__all__` and in `api.SURFACE` exists, and a name that
`api` gives at its top is the same object as the one in its submodule. Two: each import
of `slcore` in `src/` outside the core reads a name that `SURFACE` holds. A module that the
consumer imports as a module (`from slcore.rules import r08_fire`) counts by the
attributes the file reads off it.

`ALLOWED_FOR_NOW` holds the reads that are known and are not in the contract. The test
fails on a new read outside the contract, and it fails when an allowed read is gone, so
the set gets smaller.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import types
from pathlib import Path

from slcore import api

SRC = Path(__file__).resolve().parents[2] / "src"

# (file below src, "module.name"). Each one has its cause.
ALLOWED_FOR_NOW: frozenset[tuple[str, str]] = frozenset()


def is_submodule(parent: str, name: str) -> bool:
    try:
        return isinstance(getattr(importlib.import_module(parent), name, None), types.ModuleType) or importlib.util.find_spec(f"{parent}.{name}") is not None
    except ModuleNotFoundError:
        return False


def reads_of(path: Path) -> set[str]:
    """Each "module.name" of slcore that the file reads."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    reads: set[str] = set()
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.split(".")[0] == "slcore":
            for alias in node.names:
                if is_submodule(node.module, alias.name):
                    aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
                else:
                    reads.add(f"{node.module}.{alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "slcore":
                    if alias.asname:
                        aliases[alias.asname] = alias.name
                    else:
                        # `import slcore.x` reads the module by its full name.
                        reads.add(f"{alias.name}.<module>")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases:
            reads.add(f"{aliases[node.value.id]}.{node.attr}")
    return reads


def all_reads() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        if rel.startswith("slcore/") or "egg-info" in rel:
            continue
        for read in reads_of(path):
            out.add((rel, read))
    return out


def in_surface(read: str) -> bool:
    module, _, name = read.rpartition(".")
    return name in api.SURFACE.get(module, ())


def test_each_name_of_the_api_exists() -> None:
    missing = [name for name in api.__all__ if not hasattr(api, name)]
    assert not missing, f"api.__all__ names what api does not have: {missing}"


def test_each_name_of_the_surface_exists_in_its_module() -> None:
    missing = []
    for module_name, names in api.SURFACE.items():
        module = importlib.import_module(module_name)
        missing.extend(f"{module_name}.{name}" for name in names if not hasattr(module, name))
    assert not missing, f"SURFACE names what the core does not have: {missing}"


def test_a_top_name_of_the_api_is_the_object_of_its_module() -> None:
    wrong = []
    for name in api.__all__:
        value = getattr(api, name)
        if name == "SURFACE" or isinstance(value, types.ModuleType):
            continue
        owners = [m for m, names in api.SURFACE.items() if name in names]
        if not owners:
            wrong.append(f"{name} is in no SURFACE entry")
        elif not any(getattr(importlib.import_module(m), name) is value for m in owners):
            wrong.append(f"{name} is not the object of {owners}")
    assert not wrong, "\n".join(wrong)


def test_a_module_the_api_gives_is_in_the_surface() -> None:
    for name in api.__all__:
        value = getattr(api, name)
        if isinstance(value, types.ModuleType):
            assert value.__name__ in api.SURFACE, value.__name__


def test_no_consumer_reads_the_core_outside_the_api() -> None:
    outside = sorted((rel, read) for rel, read in all_reads() if not in_surface(read))
    new = [item for item in outside if item not in ALLOWED_FOR_NOW]
    assert not new, "reads of the core outside slcore.api.SURFACE:\n" + "\n".join(f"{rel} reads {read}" for rel, read in new)


def test_each_allowed_read_is_still_there() -> None:
    reads = all_reads()
    gone = sorted(item for item in ALLOWED_FOR_NOW if item not in reads)
    assert not gone, f"remove these from ALLOWED_FOR_NOW: {gone}"


def test_the_reader_counts_a_module_by_its_attributes(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "from slcore.rules import r13_rout\nfrom slcore.engine import Engine\n\ndef f(s):\n    return r13_rout.hopeless(s), r13_rout.not_in_api\n",
        encoding="utf-8",
    )
    reads = reads_of(sample)
    assert reads == {"slcore.rules.r13_rout.hopeless", "slcore.rules.r13_rout.not_in_api", "slcore.engine.Engine"}
    assert not in_surface("slcore.rules.r13_rout.not_in_api")
    assert in_surface("slcore.rules.r13_rout.hopeless")
