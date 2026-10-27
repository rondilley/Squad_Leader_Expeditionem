"""Install and start the collector of played games on a Linux host, from this workstation.

    python tools/collect_deploy.py                 tars (the first collector, owner 2026-10-27)
    python tools/collect_deploy.py HOST            another host
    python tools/collect_deploy.py --keys-only     copy the key store only, after `sl-cli collect key add`

One ssh connection (your ssh keys, as for any login) copies a tar of `src/`, the key store
`collect_keys.key.txt`, and `tools/collect_server.sh` to `~/squad_leader_collect`, and runs
that script. The games stay in `~/squad_leader_collect_data`, which a deploy does not touch.
The collector reads the key store again when it changes, so `--keys-only` needs no restart.

Check it with: curl http://tars.uberadmin.com:5170/v1/ping
"""

from __future__ import annotations

import io
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from farm_deploy import DOMAIN, USER, _add, included  # noqa: E402 - the same tar rules as the farm

DEFAULT_HOST = "tars"
STORE = "collect_keys.key.txt"
FILES = ("pyproject.toml", "README.md", STORE, "tools/collect_server.sh")
REMOTE = "rm -rf squad_leader_collect/src && mkdir -p squad_leader_collect && tar -xzf - -C squad_leader_collect && bash squad_leader_collect/tools/collect_server.sh"
REMOTE_KEYS = "mkdir -p squad_leader_collect && tar -xzf - -C squad_leader_collect && chmod 600 squad_leader_collect/" + STORE


def archive(root: Path = ROOT, keys_only: bool = False) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        if not keys_only:
            for path in sorted((root / "src").rglob("*")):
                rel = path.relative_to(root).as_posix()
                if path.is_file() and included(rel):
                    _add(tar, path, rel)
        for rel in (STORE,) if keys_only else FILES:
            _add(tar, root / rel, rel)
    return buffer.getvalue()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    keys_only = "--keys-only" in args
    hosts = [a for a in args if not a.startswith("--")] or [DEFAULT_HOST]
    if not (ROOT / STORE).is_file():
        print(f"ERROR no {STORE}; make a key with: sl-cli collect key add NAME", file=sys.stderr)
        return 1
    data = archive(keys_only=keys_only)
    failed = []
    for host in hosts:
        target = f"{USER}@{host}" if "." in host else f"{USER}@{host}.{DOMAIN}"
        print(f"== {target}", flush=True)
        try:
            done = subprocess.run(["ssh", target, REMOTE_KEYS if keys_only else REMOTE], input=data, timeout=900)
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
    print("done. Check it with: curl http://" + (hosts[0] if "." in hosts[0] else f"{hosts[0]}.{DOMAIN}") + ":5170/v1/ping")
    return 0


if __name__ == "__main__":
    sys.exit(main())
