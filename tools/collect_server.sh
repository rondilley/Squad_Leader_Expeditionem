#!/usr/bin/env bash
# Install and start the collector of played games on this Linux host (`sl-cli collect serve`).
# tools/collect_deploy.py copies the tree here (~/squad_leader_collect) and runs this script.
# It stops the old collector, makes the venv, installs the tree (no extra: the collector
# needs only the rules core and the host), and starts the collector on port 5170 in a process
# group of its own. The games go to ~/squad_leader_collect_data, outside the code folder, so
# a deploy never touches them. The run succeeds only when the new process holds the port.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT=5170
DATA="$HOME/squad_leader_collect_data"

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

if [ -f collect.pid ]; then
  pid=$(cat collect.pid)
  if kill -0 "$pid" 2>/dev/null; then
    echo "stopping the old collector ($pid)"
    stop_group "$pid"
  fi
  rm -f collect.pid
fi

if port_held; then
  held=$(listener_pid)
  if [ -z "$held" ]; then
    echo "ERROR port $PORT is held by a process of another user:"; ss -ltnH "sport = :$PORT" || true; exit 1
  fi
  if ! tr '\0' ' ' < "/proc/$held/cmdline" | grep -q "collect serve"; then
    echo "ERROR port $PORT is held by another program ($held):"; tr '\0' ' ' < "/proc/$held/cmdline"; echo; exit 1
  fi
  group=$(group_of "$held")
  echo "stopping a collector that collect.pid does not name ($held, group ${group:-none})"
  stop_group "${group:-$held}"
  for i in $(seq 1 20); do port_held || break; sleep 0.5; done
  if port_held; then
    echo "ERROR port $PORT is still held after the stop"; exit 1
  fi
fi

[ -f collect_keys.key.txt ] || { echo "ERROR no collect_keys.key.txt; make a key with: sl-cli collect key add NAME"; exit 1; }
chmod 600 collect_keys.key.txt
mkdir -p "$DATA"
chmod 700 "$DATA"

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
  echo "ERROR python3 is older than 3.12"; exit 1
fi
if [ ! -x .venv/bin/python ]; then
  echo "making the venv"
  python3 -m venv .venv || { echo "ERROR no venv; run: sudo apt install python3-venv"; exit 1; }
fi
echo "installing"
.venv/bin/python -m pip install -q --disable-pip-version-check -e .

setsid nohup .venv/bin/sl-cli collect serve --bind 0.0.0.0 --port "$PORT" --data "$DATA" --keys collect_keys.key.txt >> collect.log 2>&1 < /dev/null &
new=$!
echo "$new" > collect.pid
for i in $(seq 1 60); do
  if ! kill -0 "$new" 2>/dev/null; then
    echo "ERROR the collector stopped:"; tail -n 20 collect.log; rm -f collect.pid; exit 1
  fi
  held=$(listener_pid)
  if [ -n "$held" ] && [ "$(group_of "$held")" = "$new" ]; then
    echo "collector running on $(hostname):$PORT, data in $DATA (log: ~/squad_leader_collect/collect.log)"
    exit 0
  fi
  sleep 0.5
done
echo "ERROR the collector ($new) did not take port $PORT in 30 s:"; tail -n 20 collect.log
stop_group "$new"
rm -f collect.pid
exit 1
