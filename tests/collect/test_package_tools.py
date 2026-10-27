"""The packager (`tools/package.py`) and the deploy tool of the collector
(`tools/collect_deploy.py`), without a build and without a host.

The package must leave out the training libraries and each key file. The tar of the deploy
holds the key store with mode 600 and no other key, and the collector script must parse in bash.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from tools import collect_deploy, package

ROOT = Path(__file__).resolve().parents[2]


def test_the_package_leaves_out_the_training_libraries_and_has_the_data():
    args = package.pyinstaller_args(Path("dist"), Path("build"))
    assert args[0].endswith("frozen_main.py")
    pairs = list(zip(args, args[1:]))
    for module in ("torch", "numpy", "gymnasium"):
        assert ("--exclude-module", module) in pairs
    for data in ("sldata", "slwindow3d", "slhost"):
        assert ("--collect-data", data) in pairs
    assert ("--collect-all", "panda3d") in pairs and "--windowed" in args


def test_a_key_file_in_the_package_stops_the_build(tmp_path):
    (tmp_path / "_internal").mkdir()
    package.check_no_keys(tmp_path)
    (tmp_path / "_internal" / "farm.key.txt").write_text("k", encoding="utf-8")
    with pytest.raises(RuntimeError, match="key file"):
        package.check_no_keys(tmp_path)


def _tree(tmp_path: Path) -> Path:
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "m.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "src" / "pkg" / "other.key.txt").write_text("k", encoding="utf-8")
    (tmp_path / "tools").mkdir()
    for rel in collect_deploy.FILES:
        (tmp_path / rel).write_bytes(b"line\r\n")
    return tmp_path


def test_the_deploy_tar_holds_the_key_store_and_no_other_key(tmp_path):
    root = _tree(tmp_path)
    with tarfile.open(fileobj=io.BytesIO(collect_deploy.archive(root)), mode="r:gz") as tar:
        members = {m.name: m for m in tar.getmembers()}
        script = tar.extractfile("tools/collect_server.sh").read()
    assert set(members) == {"src/pkg/m.py", *collect_deploy.FILES}
    assert members[collect_deploy.STORE].mode == 0o600
    assert script == b"line\n", "the script goes with LF line ends"
    with tarfile.open(fileobj=io.BytesIO(collect_deploy.archive(root, keys_only=True)), mode="r:gz") as tar:
        assert tar.getnames() == [collect_deploy.STORE]


def test_the_collector_script_is_valid_bash():
    bash = shutil.which("bash")
    if bash is None:
        pytest.fail("bash is necessary for this test; Git for Windows has it")
    done = subprocess.run([bash, "-n", str(ROOT / "tools" / "collect_server.sh")], capture_output=True, timeout=30)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
