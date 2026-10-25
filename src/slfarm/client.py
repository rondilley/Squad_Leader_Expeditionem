"""The farm client: it plays one list of games on the remote hosts and the local workers.

Each host gets a thread with one connection. The thread keeps as many games in flight as
the host has slots, and it takes the next game from one shared queue. The local workers are
one more thread with a process pool of their own. A result goes in the slot of its game,
so the list comes back in the order of the jobs, whatever host played each game, and the
artifact is the one a single machine writes (TR-02).

A host that fails (the connection breaks, a result does not come in `result_timeout`
seconds, or the host refuses a job because its worker died) puts its games in flight back
on the queue, and the other hosts and the local workers play them. A game is its seed, so
the second play gives the same result. When no host and no local worker is left and games
remain, the run stops with a `FarmError`, because a rate without those games is not the
rate the run asked for.
"""

from __future__ import annotations

import json
import queue
import socket
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from slfarm import protocol as p

Job = tuple[str, int, str, str]
Play = Callable[[Job], dict[str, Any]]
Progress = Callable[[int, int, Job, dict[str, Any]], None]

CONNECT_TIMEOUT_SECONDS = 10.0
FILE_PREFIX = "file:"
RESULT_TIMEOUT_SECONDS = 1800.0


@dataclass(frozen=True)
class Address:
    host: str
    port: int

    def __str__(self) -> str:
        return f"{self.host}:{self.port}"


@dataclass(frozen=True)
class Farm:
    """The hosts of a run and the key that each connection proves.

    `slots_per_host` caps the games that the run sends to one host at a time, or None for
    each slot of the host. A game on four stacked boards holds about 2 GB in its worker, so
    30 of them at a time do not fit in a host that also runs a language model (2026-10-18).
    """

    addresses: tuple[Address, ...]
    key: bytes
    slots_per_host: int | None = None

    def __repr__(self) -> str:
        return f"Farm({', '.join(str(a) for a in self.addresses)})"


def parse_addresses(text: str) -> list[Address]:
    """`tars:5160,case` as addresses; a name with no port takes `DEFAULT_PORT`."""
    out: list[Address] = []
    for part in (piece.strip() for piece in text.split(",")):
        if not part:
            continue
        host, _, port = part.rpartition(":") if ":" in part else (part, "", "")
        if not host:
            host, port = part, ""
        try:
            number = int(port) if port else p.DEFAULT_PORT
        except ValueError as exc:
            raise ValueError(f"the farm address {part!r} has a port that is not a number") from exc
        if not 0 < number < 65536:
            raise ValueError(f"the farm address {part!r} has a port outside 1 to 65535")
        out.append(Address(host, number))
    if not out:
        raise ValueError("the farm needs one host address or more")
    return out


class Connection:
    """One authenticated connection to one farm host."""

    def __init__(self, address: Address, key: bytes, code: str, result_timeout: float = RESULT_TIMEOUT_SECONDS) -> None:
        self.address = address
        self.result_timeout = result_timeout
        try:
            self.sock = socket.create_connection((address.host, address.port), timeout=CONNECT_TIMEOUT_SECONDS)
        except OSError as exc:
            raise p.FarmError(f"cannot connect to the farm host {address}: {exc}") from exc
        self.file = self.sock.makefile("rb")
        try:
            challenge = self._receive(p.AUTH_TIMEOUT_SECONDS)
            if challenge.get("type") != "challenge":
                raise p.FarmProtocolError(f"{address} did not send a challenge")
            if challenge.get("protocol") != p.PROTOCOL:
                raise p.FarmVersionError(f"{address} speaks protocol {challenge.get('protocol')!r}, and this client speaks {p.PROTOCOL}")
            if challenge.get("code") != code:
                raise p.FarmVersionError(
                    f"{address} runs other code (hash {str(challenge.get('code'))[:12]}, here {code[:12]}); "
                    "copy this tree to the host and start its server again"
                )
            slots = challenge.get("slots")
            if not isinstance(slots, int) or slots < 1:
                raise p.FarmProtocolError(f"{address} gave {slots!r} slots")
            self.slots = slots
            self.send({"type": "auth", "mac": p.mac_of(key, str(challenge.get("nonce", "")))})
            answer = self._receive(p.AUTH_TIMEOUT_SECONDS)
            if answer.get("type") != "ready":
                raise p.FarmAuthError(f"{address} refused the key: {answer.get('error', answer.get('type'))}")
        except BaseException:
            self.close()
            raise

    def send(self, message: dict[str, Any]) -> None:
        try:
            self.sock.sendall(p.encode(message))
        except OSError as exc:
            raise p.FarmError(f"the connection to {self.address} failed: {exc}") from exc

    def _receive(self, timeout: float) -> dict[str, Any]:
        self.sock.settimeout(timeout)
        try:
            line = self.file.readline(p.MAX_LINE + 1)
        except socket.timeout as exc:
            raise p.FarmError(f"{self.address} sent nothing in {timeout:.0f} s") from exc
        except OSError as exc:
            raise p.FarmError(f"the connection to {self.address} failed: {exc}") from exc
        if not line:
            raise p.FarmError(f"{self.address} closed the connection")
        return p.decode(line)

    def receive(self) -> dict[str, Any]:
        return self._receive(self.result_timeout)

    def ping(self) -> dict[str, Any]:
        self.send({"type": "ping"})
        return self._receive(p.AUTH_TIMEOUT_SECONDS)

    def close(self) -> None:
        try:
            self.file.close()
        finally:
            self.sock.close()


def _document(path: str) -> Any:
    """The JSON document of a scenario file, checked as a host checks it."""
    from sldata.loaders import DataError, read_json_file, scenario_from_document

    try:
        data = read_json_file(path)
        scenario_from_document(data, f"scenario file {path}")
    except DataError as exc:
        raise p.JobRefused(str(exc)) from exc
    if len(json.dumps(data)) > p.MAX_LINE // 2:
        raise p.JobRefused(f"the scenario file {path} is too large to send")
    return data


class _Run:
    """The state that the threads of one run share."""

    def __init__(self, jobs: Sequence[Job], progress: Progress | None) -> None:
        self.jobs = list(jobs)
        self.todo: queue.Queue[int] = queue.Queue()
        for index in range(len(self.jobs)):
            self.todo.put(index)
        self.results: dict[int, dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.progress = progress
        self.failures: list[str] = []
        # The document of each `file:` scenario: a host has no such file, so the job
        # carries the document.
        self.documents: dict[str, Any] = {}
        for scenario in {job[0] for job in self.jobs}:
            if scenario.startswith(FILE_PREFIX):
                self.documents[scenario] = _document(scenario[len(FILE_PREFIX) :])
        if not self.jobs:
            self.done.set()

    def take(self) -> int | None:
        try:
            return self.todo.get_nowait()
        except queue.Empty:
            return None

    def put_back(self, indexes: Sequence[int]) -> None:
        for index in indexes:
            if index not in self.results:
                self.todo.put(index)

    def finish(self, index: int, outcome: dict[str, Any]) -> None:
        with self.lock:
            if index in self.results:
                return
            self.results[index] = outcome
            count = len(self.results)
            if self.progress is not None:
                self.progress(count, len(self.jobs), self.jobs[index], outcome)
            if count == len(self.jobs):
                self.done.set()


def _host_thread(run: _Run, connection: Connection) -> None:
    flight: set[int] = set()
    refusals = 0
    try:
        while not run.done.is_set():
            while len(flight) < connection.slots:
                index = run.take()
                if index is None:
                    break
                # In flight before the send, so a send that fails puts the game back too.
                flight.add(index)
                scenario, seed, first, second = run.jobs[index]
                message: dict[str, Any] = {"type": "job", "id": index, "seed": seed, "agents": [first, second]}
                document = run.documents.get(scenario)
                if document is not None:
                    message["scenario_doc"] = document
                else:
                    message["scenario"] = scenario
                connection.send(message)
            if not flight:
                if run.todo.empty():
                    # Games are in flight on other threads; one may come back to the queue.
                    run.done.wait(0.2)
                continue
            message = connection.receive()
            kind = message.get("type")
            index = message.get("id")
            if kind == "result" and index in flight:
                flight.discard(index)
                run.finish(index, message["outcome"])
            elif kind == "refused" and index in flight:
                # The host runs this code, so it refuses a job of this list only when its
                # worker died. The game goes back on the queue for another slot, and a host
                # that refuses three games is out of the run.
                flight.discard(index)
                run.put_back([index])
                refusals += 1
                if refusals >= 3:
                    raise p.FarmError(f"{connection.address} refused {refusals} games, the last: {message.get('error')}")
            else:
                raise p.FarmProtocolError(f"{connection.address} sent {kind!r} for job {index!r}")
    except p.FarmError as exc:
        run.failures.append(str(exc))
    finally:
        run.put_back(sorted(flight))
        connection.close()


def _local_thread(run: _Run, workers: int, play: Play) -> None:
    flight: dict[Any, int] = {}
    try:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            while not run.done.is_set():
                while len(flight) < workers:
                    index = run.take()
                    if index is None:
                        break
                    flight[pool.submit(play, run.jobs[index])] = index
                if not flight:
                    run.done.wait(0.2)
                    continue
                finished, _ = wait(list(flight), timeout=0.5, return_when=FIRST_COMPLETED)
                for future in finished:
                    index = flight.pop(future)
                    run.finish(index, future.result())
    except BrokenProcessPool:
        run.failures.append("a local worker process died")
    finally:
        run.put_back(sorted(flight.values()))


def host_slots(slots: int, cap: int | None) -> int:
    """The games that a run sends to one host at a time: its slots, or the cap when lower."""
    if cap is None:
        return slots
    if cap < 1:
        raise ValueError(f"the slots for each host must be 1 or more, not {cap}")
    return min(slots, cap)


def play_all(
    jobs: Sequence[Job],
    addresses: Sequence[Address],
    key: bytes,
    local_workers: int = 0,
    play: Play | None = None,
    progress: Progress | None = None,
    result_timeout: float = RESULT_TIMEOUT_SECONDS,
    slots_per_host: int | None = None,
) -> list[dict[str, Any]]:
    """The outcome of each job, in the order of the jobs."""
    p.check_agents_for_farm(sorted({name for job in jobs for name in job[2:]}))
    code = p.code_hash()
    connections = [Connection(address, key, code, result_timeout) for address in addresses]
    for connection in connections:
        connection.slots = host_slots(connection.slots, slots_per_host)
    run = _Run(jobs, progress)
    threads = [threading.Thread(target=_host_thread, args=(run, c), daemon=True) for c in connections]
    if local_workers > 0:
        if play is None:
            raise ValueError("local workers need the function that plays one game")
        threads.append(threading.Thread(target=_local_thread, args=(run, local_workers, play), daemon=True))
    for thread in threads:
        thread.start()
    while not run.done.is_set():
        if not any(thread.is_alive() for thread in threads):
            break
        run.done.wait(0.5)
    run.done.set()
    for thread in threads:
        thread.join(60)
    missing = len(jobs) - len(run.results)
    if missing:
        detail = "; ".join(run.failures[-3:]) or "no host is left"
        raise p.FarmError(f"{missing} of {len(jobs)} games have no result: {detail}")
    return [run.results[index] for index in range(len(jobs))]


def ping(addresses: Sequence[Address], key: bytes) -> list[dict[str, Any]]:
    """For each host: its address, and its slots and busy count, or the error."""
    code = p.code_hash()
    out: list[dict[str, Any]] = []
    for address in addresses:
        started = time.perf_counter()
        try:
            connection = Connection(address, key, code)
        except p.FarmError as exc:
            out.append({"address": str(address), "error": str(exc)})
            continue
        try:
            pong = connection.ping()
            out.append({"address": str(address), "slots": pong.get("slots"), "busy": pong.get("busy"), "envs": pong.get("envs", 0), "seconds": round(time.perf_counter() - started, 3)})
        except p.FarmError as exc:
            out.append({"address": str(address), "error": str(exc)})
        finally:
            connection.close()
    return out


# ------------------------------------------------------------------ the PPO environments


class RemoteEnvError(p.FarmError):
    """A remote PPO environment that failed: the host refused it, or it stopped."""


def open_env(
    address: Address, key: bytes, scenario: str, index: int, seed: int, max_commands: int,
    result_timeout: float = RESULT_TIMEOUT_SECONDS,
) -> Connection:
    """A connection that holds one PPO environment on the host."""
    connection = Connection(address, key, p.code_hash(), result_timeout)
    message: dict[str, Any] = {"type": "env_open", "index": index, "seed": seed, "max_commands": max_commands}
    if scenario.startswith(FILE_PREFIX):
        message["scenario_doc"] = _document(scenario[len(FILE_PREFIX) :])
    else:
        message["scenario"] = scenario
    try:
        connection.send(message)
        answer = connection._receive(p.AUTH_TIMEOUT_SECONDS * 3)
    except BaseException:
        connection.close()
        raise
    if answer.get("type") != "env_ready":
        connection.close()
        raise RemoteEnvError(f"{address} did not open environment {index}: {answer.get('error', answer.get('type'))}")
    return connection


def bridge(local: Any, connection: Connection) -> None:
    """The thread between the trainer's pipe end and one remote environment.

    The trainer sends the tuples of `worker_main` on its pipe, and this thread sends each
    one to the host and puts the decision of the host on the pipe. When the host fails,
    the thread closes the pipe, and the trainer's next receive sees the end of the pipe.
    """
    from slfarm import envwire

    try:
        while True:
            try:
                command = local.recv()
            except (EOFError, OSError):
                break
            connection.send({"type": "env", "command": envwire.encode_command(command)})
            if command[0] == "stop":
                break
            answer = connection.receive()
            if answer.get("type") != "env_decision":
                raise RemoteEnvError(f"{connection.address}: {answer.get('error', answer.get('type'))}")
            local.send(envwire.decode_decision(answer))
    except p.FarmError as exc:
        print(f"farm: environment on {connection.address} stopped: {exc}", file=sys.stderr, flush=True)
    finally:
        connection.close()
        local.close()


BRIDGE_OPEN_SECONDS = 300.0
BRIDGE_OPEN_THREADS = 8


def host_bridge_main(
    control: Any, pipes: Sequence[Any], address: Address, key: bytes, scenario: str,
    first_index: int, seed: int, max_commands: int,
) -> None:
    """The process that holds the PPO environments of one host for a trainer.

    It opens one environment for each pipe end, says on `control` that they are open (or
    why not), and runs a `bridge` thread for each. The JSON and the base64 of the decisions
    take the interpreter lock of this process, not the one of the trainer: with the bridges
    in the trainer, 44 remote workers gave fewer steps per second than 16 local ones
    (2026-10-14). Environment `first_index + n` has the seed of the local worker of that
    index, `seed + index * 1_000_003`.
    """
    from concurrent.futures import ThreadPoolExecutor

    def one(offset: int) -> Connection:
        index = first_index + offset
        return open_env(address, key, scenario, index, seed + index * 1_000_003, max_commands)

    # The environments open in parallel; the host starts a process for each one.
    with ThreadPoolExecutor(max_workers=max(1, min(len(pipes), BRIDGE_OPEN_THREADS))) as pool:
        futures = [pool.submit(one, offset) for offset in range(len(pipes))]
    connections: list[Connection] = []
    failures: list[str] = []
    for future in futures:
        try:
            connections.append(future.result())
        except Exception as exc:
            failures.append(f"{type(exc).__name__}: {exc}")
    if failures:
        for connection in connections:
            connection.close()
        control.send(("error", failures[0]))
        return
    control.send(("ready", len(connections)))
    threads = [
        threading.Thread(target=bridge, args=(pipe, connection), daemon=True, name=f"sl-remote-{first_index + n}")
        for n, (pipe, connection) in enumerate(zip(pipes, connections))
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
