#!/usr/bin/env bash
# Install and start the game farm worker on this Linux host (`sl-cli farm serve`).
# tools/farm_deploy.py copies the tree here (~/squad_leader) and runs this script.
# It stops the old worker, makes the venv, installs the tree, and starts the worker on
# port 5160 in a process group of its own, so the next run stops its game processes too.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f farm.pid ]; then
  pid=$(cat farm.pid)
  if kill -0 "$pid" 2>/dev/null; then
    echo "stopping the old worker ($pid)"
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    for i in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
    kill -KILL -- "-$pid" 2>/dev/null || true
  fi
  rm -f farm.pid
fi

chmod 600 farm.key.txt

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
  echo "ERROR python3 is older than 3.12"; exit 1
fi
if [ ! -x .venv/bin/python ]; then
  echo "making the venv"
  python3 -m venv .venv || { echo "ERROR no venv; run: sudo apt install python3-venv"; exit 1; }
fi
echo "installing"
# The PPO workers need torch and numpy (the train extra). The CPU build of torch is a
# tenth of the size of the default build, and a worker uses no graphics card.
if ! .venv/bin/python -c 'import torch' 2>/dev/null; then
  echo "installing torch (CPU)"
  .venv/bin/python -m pip install -q --disable-pip-version-check torch --index-url https://download.pytorch.org/whl/cpu
fi
.venv/bin/python -m pip install -q --disable-pip-version-check -e ".[train]"

slots=$(( $(nproc) - 2 ))
[ "$slots" -ge 1 ] || slots=1
setsid nohup .venv/bin/sl-cli farm serve --host 0.0.0.0 --port 5160 --slots "$slots" --key farm.key.txt > farm.log 2>&1 < /dev/null &
echo $! > farm.pid
sleep 3
if ! kill -0 "$(cat farm.pid)" 2>/dev/null; then
  echo "ERROR the worker stopped:"; tail -n 20 farm.log; exit 1
fi
echo "worker running on $(hostname):5160 with $slots slots (log: ~/squad_leader/farm.log)"
