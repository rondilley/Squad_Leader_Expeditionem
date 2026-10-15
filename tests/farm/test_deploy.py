"""The deploy tool of the game farm (`tools/farm_deploy.py`) and the worker script, without a host.

A worker takes the code only when its hash of `src/` is the hash of this tree, so the tar
the tool sends must unpack to a tree with that hash. The tar holds the worker key with mode
600 and no other key, and the worker script must parse in bash.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from slfarm import protocol
from tools import farm_deploy as deploy

ROOT = Path(__file__).resolve().parents[2]


def _tree(tmp_path: Path) -> Path:
    """A small tree with the files of the tar, a key inside `src/`, and a compiled file."""
    (tmp_path / "src" / "pkg" / "__pycache__").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "m.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "src" / "pkg" / "other.key.txt").write_text("k" * 64, encoding="utf-8")
    (tmp_path / "src" / "pkg" / "__pycache__" / "m.cpython-312.pyc").write_bytes(b"\0")
    (tmp_path / "tools").mkdir()
    for rel in deploy.FILES:
        (tmp_path / rel).write_bytes(b"line\r\n")
    return tmp_path


def test_the_tar_unpacks_to_the_code_hash_of_this_tree(tmp_path: Path):
    if not (ROOT / "farm.key.txt").is_file():
        pytest.fail("make the worker key first: sl-cli farm key --write farm.key.txt")
    with tarfile.open(fileobj=io.BytesIO(deploy.archive()), mode="r:gz") as tar:
        tar.extractall(tmp_path, filter="data")
    assert protocol.code_hash(tmp_path / "src") == protocol.code_hash()
    assert (tmp_path / "tools" / "farm_worker.sh").is_file()


def test_the_tar_holds_the_worker_key_and_no_other(tmp_path: Path):
    with tarfile.open(fileobj=io.BytesIO(deploy.archive(_tree(tmp_path))), mode="r:gz") as tar:
        members = {m.name: m for m in tar.getmembers()}
        script = tar.extractfile("tools/farm_worker.sh").read()
    assert set(members) == {"src/pkg/m.py", *deploy.FILES}
    assert members["farm.key.txt"].mode == 0o600
    assert script == b"line\n", "the worker script goes with LF line ends"


def test_the_worker_script_is_valid_bash():
    bash = shutil.which("bash")
    if bash is None:
        pytest.fail("bash is necessary for this test; Git for Windows has it")
    done = subprocess.run([bash, "-n", str(ROOT / "tools" / "farm_worker.sh")], capture_output=True, timeout=30)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
