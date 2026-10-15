"""The farm server: it plays the games that an authenticated client sends.

One process listens. A pool of `slots` worker processes plays the games, and each
connection may have games in the pool at the same time; the pool is the limit. The function
that plays one game comes from the caller (`slcli.farm_cmd` gives the one of the gauntlet),
so this package does not import the command line.

A worker process that dies loses its game. The server answers that job with `refused`,
makes a new pool, and goes on; the client plays the game again on another slot, and a game
is its seed, so the result is the same.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from typing import Any, Callable

from slfarm import protocol as p

Play = Callable[[tuple[Any, int, str, str]], dict[str, Any]]


def _log(text: str) -> None:
    print(f"farm: {text}", file=sys.stderr, flush=True)


class FarmServer:
    def __init__(
        self,
        key: bytes,
        play: Play,
        scenarios: frozenset[str],
        slots: int,
        code: str | None = None,
        log: Callable[[str], None] = _log,
        env_main: Callable[..., None] | None = None,
    ) -> None:
        if slots < 1:
            raise ValueError(f"a farm server needs one slot or more, not {slots}")
        self.key = key
        self.play = play
        self.scenarios = scenarios
        self.slots = slots
        self.code = code or p.code_hash()
        self.log = log
        self.busy = 0
        # The PPO environment loop (`slagents.learned.workers.worker_main`), or None on a
        # host with no `train` extra, and the count of environments open now.
        self.env_main = env_main
        self.envs = 0
        self._pool: ProcessPoolExecutor | None = None
        self._server: asyncio.base_events.Server | None = None

    # ------------------------------------------------------------------ the pool

    def _executor(self) -> ProcessPoolExecutor:
        if self._pool is None:
            self._pool = ProcessPoolExecutor(max_workers=self.slots)
        return self._pool

    def _renew_pool(self) -> None:
        old, self._pool = self._pool, None
        if old is not None:
            old.shutdown(wait=False, cancel_futures=True)

    async def _run(self, game: tuple[Any, int, str, str]) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        self.busy += 1
        try:
            return await loop.run_in_executor(self._executor(), self.play, game)
        finally:
            self.busy -= 1

    # ------------------------------------------------------------- a connection

    async def _send(self, writer: asyncio.StreamWriter, lock: asyncio.Lock, message: dict[str, Any]) -> None:
        async with lock:
            writer.write(p.encode(message))
            await writer.drain()

    async def _read(self, reader: asyncio.StreamReader) -> dict[str, Any] | None:
        try:
            line = await reader.readuntil(b"\n")
        except asyncio.IncompleteReadError:
            return None
        except asyncio.LimitOverrunError as exc:
            raise p.FarmProtocolError(f"a line longer than {p.MAX_LINE} bytes") from exc
        return p.decode(line)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        lock = asyncio.Lock()
        tasks: set[asyncio.Task] = set()
        try:
            nonce = p.new_nonce()
            await self._send(writer, lock, {"type": "challenge", "protocol": p.PROTOCOL, "nonce": nonce, "code": self.code, "slots": self.slots})
            try:
                auth = await asyncio.wait_for(self._read(reader), p.AUTH_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                self.log(f"{peer}: no answer to the challenge in {p.AUTH_TIMEOUT_SECONDS} s")
                return
            if auth is None or auth.get("type") != "auth" or not p.mac_matches(self.key, nonce, auth.get("mac")):
                self.log(f"{peer}: the key did not match")
                await self._send(writer, lock, {"type": "error", "error": "the key did not match"})
                return
            await self._send(writer, lock, {"type": "ready"})
            self.log(f"{peer}: connected")
            while True:
                message = await self._read(reader)
                if message is None:
                    break
                kind = message["type"]
                if kind == "ping":
                    await self._send(writer, lock, {"type": "pong", "slots": self.slots, "busy": self.busy, "envs": self.envs})
                elif kind == "env_open":
                    # The connection holds one PPO environment for the rest of its life.
                    await self._env_session(reader, writer, lock, message, peer)
                    break
                elif kind == "job":
                    try:
                        job_id, game = p.check_job(message, self.scenarios)
                    except p.JobRefused as exc:
                        await self._send(writer, lock, {"type": "refused", "id": message.get("id"), "error": str(exc)})
                        continue
                    task = asyncio.create_task(self._job(writer, lock, job_id, game))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
                else:
                    raise p.FarmProtocolError(f"a message of type {kind!r} is not one of the protocol")
        except p.FarmProtocolError as exc:
            self.log(f"{peer}: {exc}")
        except (ConnectionError, OSError) as exc:
            self.log(f"{peer}: the connection failed: {exc}")
        finally:
            for task in tasks:
                task.cancel()
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def _env_session(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, lock: asyncio.Lock, message: dict[str, Any], peer: Any) -> None:
        """One PPO environment in a process of its own, for the life of the connection.

        The process runs `env_main`, the loop of a local PPO worker, and this side passes it
        the commands the trainer sends and sends back each decision. The commands and the
        decisions are checked JSON (`slfarm.envwire`). Each environment takes one slot.
        """
        import multiprocessing as mp

        from slfarm import envwire

        if self.env_main is None:
            await self._send(writer, lock, {"type": "env_error", "error": "this host has no PPO environment; install the train extra"})
            return
        try:
            scenario, index, seed, max_commands = p.check_env_open(message, self.scenarios)
        except p.JobRefused as exc:
            await self._send(writer, lock, {"type": "env_error", "error": str(exc)})
            return
        if self.envs >= self.slots:
            await self._send(writer, lock, {"type": "env_error", "error": f"all {self.slots} slots of this host hold environments"})
            return
        loop = asyncio.get_running_loop()
        context = mp.get_context("spawn")
        ours, theirs = context.Pipe()
        process = context.Process(target=self.env_main, args=(theirs, scenario, index, seed, max_commands), daemon=True)
        self.envs += 1
        try:
            process.start()
            theirs.close()
            await self._send(writer, lock, {"type": "env_ready"})
            while True:
                request = await self._read(reader)
                if request is None or request.get("type") != "env":
                    break
                try:
                    command = envwire.check_command(request.get("command"))
                except p.JobRefused as exc:
                    await self._send(writer, lock, {"type": "env_error", "error": str(exc)})
                    break
                ours.send(command)
                if command[0] == "stop":
                    break
                try:
                    decision = await loop.run_in_executor(None, ours.recv)
                except (EOFError, OSError):
                    await self._send(writer, lock, {"type": "env_error", "error": "the environment process stopped"})
                    break
                await self._send(writer, lock, envwire.encode_decision(decision))
        finally:
            try:
                ours.send(("stop",))
            except (OSError, ValueError):
                pass
            await loop.run_in_executor(None, process.join, 10.0)
            if process.is_alive():
                process.terminate()
            ours.close()
            self.envs -= 1
            self.log(f"{peer}: environment {index} closed")

    async def _job(self, writer: asyncio.StreamWriter, lock: asyncio.Lock, job_id: int, game: tuple[Any, int, str, str]) -> None:
        try:
            outcome = await self._run(game)
        except BrokenProcessPool:
            self._renew_pool()
            message: dict[str, Any] = {"type": "refused", "id": job_id, "error": "the worker process died while it played this game"}
        except Exception as exc:
            # A game that cannot start (a scenario document whose board the generator
            # cannot make) is a game error of the run, as the gauntlet records it, so the
            # client does not wait for an answer that never comes.
            message = {"type": "result", "id": job_id, "outcome": {"winner": None, "error": type(exc).__name__, "message": str(exc)[:300]}}
        else:
            message = {"type": "result", "id": job_id, "outcome": outcome}
        try:
            await self._send(writer, lock, message)
        except (ConnectionError, OSError):
            pass

    # ------------------------------------------------------------- start and stop

    async def start(self, host: str, port: int) -> tuple[str, int]:
        self._server = await asyncio.start_server(self._handle, host, port, limit=p.MAX_LINE)
        bound = self._server.sockets[0].getsockname()
        return str(bound[0]), int(bound[1])

    async def serve_forever(self, host: str, port: int) -> None:
        address = await self.start(host, port)
        self.log(f"listening on {address[0]}:{address[1]} with {self.slots} slots, code {self.code[:12]}")
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    def close(self) -> None:
        if self._server is not None:
            self._server.close()
        self._renew_pool()


class ServerThread:
    """A farm server on an event loop in a thread of this process, for the tests and for
    a workstation that serves its own cores too."""

    def __init__(self, server: FarmServer, host: str = "127.0.0.1", port: int = 0) -> None:
        self.server = server
        self.loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self.address: tuple[str, int] = (host, port)
        self._error: BaseException | None = None
        self._thread = threading.Thread(target=self._main, args=(host, port), daemon=True)

    def _main(self, host: str, port: int) -> None:
        asyncio.set_event_loop(self.loop)
        try:
            self.address = self.loop.run_until_complete(self.server.start(host, port))
        except BaseException as exc:  # the caller gets it from start()
            self._error = exc
            self._ready.set()
            return
        self._ready.set()
        self.loop.run_forever()
        # The connection tasks close their streams on this loop, so they end before it closes.
        pending = [task for task in asyncio.all_tasks(self.loop) if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self.loop.close()

    def start(self) -> tuple[str, int]:
        self._thread.start()
        self._ready.wait(30)
        if self._error is not None:
            raise p.FarmError(f"the farm server did not start: {self._error}") from self._error
        return self.address

    def stop(self) -> None:
        def _close() -> None:
            self.server.close()
            self.loop.stop()

        self.loop.call_soon_threadsafe(_close)
        self._thread.join(30)
