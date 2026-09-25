"""`sl-cli` on a base install (B8).

Each test runs `sl-cli` in a new Python process that cannot import the libraries of the
optional extras. A finder at the front of `sys.meta_path` refuses them, as on a machine
that has only the base install. The help of each command must work, and a command that
needs an extra must give the typed error that names the extra, with exit code 4.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BLOCKED = ("pygame", "torch", "numpy", "panda3d", "transformers", "peft", "datasets", "accelerate", "pettingzoo", "gymnasium")

RUNNER = """
import sys

BLOCKED = set(sys.argv[1].split(","))


class Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return None


sys.meta_path.insert(0, Blocker())
from slcli.main import main

code = 0
try:
    code = main(sys.argv[2:])
except SystemExit as exc:
    code = exc.code or 0
loaded = sorted(n for n in sys.modules if n.split(".")[0] in BLOCKED)
print("LOADED=" + ",".join(loaded))
sys.exit(code)
"""


def run_cli(*argv: str, blocked: tuple[str, ...] = BLOCKED, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-c", RUNNER, ",".join(blocked), *argv],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        cwd=str(cwd or ROOT),
    )


def test_main_help_needs_no_extra():
    result = run_cli("--help")
    assert result.returncode == 0, result.stderr
    assert "cards" in result.stdout
    assert "LOADED=\n" in result.stdout


def test_cards_help_needs_no_pygame():
    result = run_cli("cards", "--help")
    assert result.returncode == 0, result.stderr
    assert "--scenario" in result.stdout
    assert "LOADED=\n" in result.stdout


def test_cards_without_pygame_gives_the_typed_error(tmp_path):
    result = run_cli("cards", "--out", str(tmp_path / "cards"))
    assert result.returncode == 4, (result.stdout, result.stderr)
    assert "pygame-ce" in result.stderr
    assert '.[desktop]' in result.stderr
    assert "Traceback" not in result.stderr


def test_learned_agent_without_torch_gives_the_typed_error(tmp_path):
    result = run_cli("play", "--agent-a", "learned:missing.pt", "--games", "1", cwd=tmp_path)
    assert result.returncode == 4, (result.stdout, result.stderr)
    assert "torch" in result.stderr
    assert '.[train]' in result.stderr
    assert "Traceback" not in result.stderr


def test_train_without_torch_names_the_extra():
    result = run_cli("train", "--updates", "1")
    assert result.returncode == 4, (result.stdout, result.stderr)
    assert '.[train]' in result.stderr
    result = run_cli("imitate")
    assert result.returncode == 4, (result.stdout, result.stderr)
    assert '.[train]' in result.stderr


def test_finetune_without_torch_names_the_extra(tmp_path):
    data = tmp_path / "traces.jsonl"
    sample = {"game_id": "g1", "board_source": "generated", "prompt": "p", "completion": "c", "weight": 1}
    data.write_text(json.dumps(sample) + "\n", encoding="utf-8")
    result = run_cli("finetune", "--smoke", "--data", str(data), "--out", str(tmp_path / "out"), cwd=tmp_path)
    assert result.returncode == 4, (result.stdout, result.stderr)
    assert "pip install" in result.stderr
    assert "Traceback" not in result.stderr


def test_unknown_argument_is_still_an_error():
    result = run_cli("cards", "--no-such-option")
    assert result.returncode == 2
    assert "unrecognized arguments: --no-such-option" in result.stderr


def test_window_without_pygame_gives_the_typed_error():
    result = run_cli("window")
    assert result.returncode == 4, (result.stdout, result.stderr)
    assert '.[desktop]' in result.stderr
