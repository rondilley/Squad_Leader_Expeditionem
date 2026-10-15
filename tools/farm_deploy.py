"""Install and start the game farm worker on Linux hosts, from this workstation.

    python tools/farm_deploy.py tars              one host
    python tools/farm_deploy.py                   tars, case, kipp, and plex

For each host, one ssh connection (your ssh keys, as for any login) copies a tar of this
tree, the worker key `farm.key.txt`, and `tools/farm_worker.sh` to `~/squad_leader`, and runs
that script there. The script installs the tree in a venv and starts `sl-cli farm serve` on
port 5160. Run it again after each change of the code: a worker refuses a workstation with
other code. Then `sl-cli gauntlet` and `sl-cli evolve` take `--remote tars,case,kipp,plex`.
"""

from __future__ import annotations

import io
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOSTS = ("tars", "case", "kipp", "plex")
USER = "rdilley"
DOMAIN = "uberadmin.com"
FILES = ("pyproject.toml", "README.md", "farm.key.txt", "tools/farm_worker.sh")
REMOTE = "rm -rf squad_leader/src && mkdir -p squad_leader && tar -xzf - -C squad_leader && bash squad_leader/tools/farm_worker.sh"


def included(rel: str) -> bool:
    """A file of `src/` that a host needs: no compiled file, no package metadata, no key."""
    parts = rel.split("/")
    if "__pycache__" in parts or any(p.endswith(".egg-info") for p in parts):
        return False
    return not rel.endswith((".pyc", ".pyo", ".key.txt"))


def _add(tar: tarfile.TarFile, path: Path, rel: str) -> None:
    data = path.read_bytes()
    if rel.endswith(".sh"):
        data = data.replace(b"\r\n", b"\n")
    info = tarfile.TarInfo(rel)
    info.size = len(data)
    info.mode = 0o600 if rel.endswith(".key.txt") else 0o644
    tar.addfile(info, io.BytesIO(data))


def archive(root: Path = ROOT) -> bytes:
    """The tar that goes to each host: `src/` and `FILES`."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for path in sorted((root / "src").rglob("*")):
            rel = path.relative_to(root).as_posix()
            if path.is_file() and included(rel):
                _add(tar, path, rel)
        for rel in FILES:
            _add(tar, root / rel, rel)
    return buffer.getvalue()


def main(argv: list[str] | None = None) -> int:
    hosts = (argv if argv is not None else sys.argv[1:]) or list(HOSTS)
    if not (ROOT / "farm.key.txt").is_file():
        print("ERROR no farm.key.txt; make one with: sl-cli farm key --write farm.key.txt", file=sys.stderr)
        return 1
    data = archive()
    failed = []
    for host in hosts:
        target = f"{USER}@{host}" if "." in host else f"{USER}@{host}.{DOMAIN}"
        print(f"== {target}", flush=True)
        try:
            done = subprocess.run(["ssh", target, REMOTE], input=data, timeout=900)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"ERROR {host}: {exc}", file=sys.stderr)
            failed.append(host)
            continue
        if done.returncode != 0:
            print(f"ERROR {host}: exit {done.returncode}", file=sys.stderr)
            failed.append(host)
    if failed:
        print(f"failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"done. Check them with: sl-cli farm ping --remote {','.join(hosts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
