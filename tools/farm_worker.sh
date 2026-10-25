#!/usr/bin/env bash
# Install and start the game farm worker on this Linux host (`sl-cli farm serve`).
# tools/farm_deploy.py copies the tree here (~/squad_leader) and runs this script.
# It stops the old worker, makes the venv, installs the tree, and starts the worker on
# port 5160 in a process group of its own, so the next run stops its game processes too.
# The run succeeds only when the new process group holds the port (2026-10-25: an old
# server that farm.pid did not name kept the port, and the ping found the old code).
set -euo pipefail
cd "$(dirname "$0")/.."
PORT=5160

# The process that listens on the port, or nothing. `ss` shows the process of this user only.
listener_pid() {
  { ss -ltnpH "sport = :$PORT" | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -n 1; } || true
}
port_held() {
  [ -n "$(ss -ltnH "sport = :$PORT" || true)" ]
}
group_of() {
  ps -o pgid= -p "$1" 2>/dev/null | tr -d ' ' || true
}
stop_group() {
  kill -TERM -- "-$1" 2>/dev/null || kill -TERM "$1" 2>/dev/null || true
  for i in $(seq 1 20); do kill -0 "$1" 2>/dev/null || break; sleep 0.5; done
  kill -KILL -- "-$1" 2>/dev/null || true
}

if [ -f farm.pid ]; then
  pid=$(cat farm.pid)
  if kill -0 "$pid" 2>/dev/null; then
    echo "stopping the old worker ($pid)"
    stop_group "$pid"
  fi
  rm -f farm.pid
fi

# A farm server that farm.pid does not name still holds the port: stop its process group.
if port_held; then
  held=$(listener_pid)
  if [ -z "$held" ]; then
    echo "ERROR port $PORT is held by a process of another user:"; ss -ltnH "sport = :$PORT" || true; exit 1
  fi
  if ! tr '\0' ' ' < "/proc/$held/cmdline" | grep -q "farm serve"; then
    echo "ERROR port $PORT is held by another program ($held):"; tr '\0' ' ' < "/proc/$held/cmdline"; echo; exit 1
  fi
  group=$(group_of "$held")
  echo "stopping a farm server that farm.pid does not name ($held, group ${group:-none})"
  stop_group "${group:-$held}"
  for i in $(seq 1 20); do port_held || break; sleep 0.5; done
  if port_held; then
    echo "ERROR port $PORT is still held after the stop"; exit 1
  fi
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
setsid nohup .venv/bin/sl-cli farm serve --host 0.0.0.0 --port "$PORT" --slots "$slots" --key farm.key.txt > farm.log 2>&1 < /dev/null &
new=$!
echo "$new" > farm.pid
# The server binds the port after it starts its pool, so wait for the bind, up to 60 s.
for i in $(seq 1 120); do
  if ! kill -0 "$new" 2>/dev/null; then
    echo "ERROR the worker stopped:"; tail -n 20 farm.log; rm -f farm.pid; exit 1
  fi
  held=$(listener_pid)
  if [ -n "$held" ] && [ "$(group_of "$held")" = "$new" ]; then
    echo "worker running on $(hostname):$PORT with $slots slots (log: ~/squad_leader/farm.log)"
    exit 0
  fi
  sleep 0.5
done
echo "ERROR the worker ($new) did not take port $PORT in 60 s:"; tail -n 20 farm.log
stop_group "$new"
rm -f farm.pid
exit 1
