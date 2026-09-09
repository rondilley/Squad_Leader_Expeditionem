"""A host inside the window's own process.

`sl-cli window` with no address starts one. The window then reaches it over a socket on
the loopback address, which is the same path the browser client takes, so the window keeps
no rule of its own (AR-06). The port is chosen by the system, so two windows on one
machine do not collide.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from dataclasses import dataclass
from typing import Any

from slhost.server import DEFAULT_HOST, Host

START_TIMEOUT = 10.0
STOP_TIMEOUT = 5.0


class HostDidNotStart(Exception):
    """The embedded host did not bind a port inside the timeout."""


@dataclass
class Embedded:
    host: Host
    port: int
    thread: threading.Thread
    loop: asyncio.AbstractEventLoop
    done: "asyncio.Event"

    @property
    def url(self) -> str:
        return f"ws://{DEFAULT_HOST}:{self.port}/"

    @property
    def room_code(self) -> str:
        return self.host.room.code

    def stop(self) -> None:
        """Ask the loop to finish serving, so the server closes before the loop does.

        Stopping the loop from outside leaves the server half closed, and its own clean-up
        then tries to make a task on a loop that is gone.
        """
        if self.loop.is_closed():
            return
        self.loop.call_soon_threadsafe(self.done.set)
        self.thread.join(timeout=STOP_TIMEOUT)


def start(host: Host, address: str = DEFAULT_HOST) -> Embedded:
    """Run the host on a thread of its own and give back the port it bound."""
    ready = threading.Event()
    holder: dict[str, Any] = {}

    def run() -> None:
        loop = _server_loop()
        asyncio.set_event_loop(loop)
        holder["loop"] = loop

        async def serve() -> None:
            done = asyncio.Event()
            holder["done"] = done
            async with host.start(address, 0) as server:
                holder["port"] = Host.bound_port(server)
                ready.set()
                await done.wait()
                server.close()

        try:
            loop.run_until_complete(serve())
        finally:
            ready.set()
            _drain(loop)
            loop.close()

    thread = threading.Thread(target=run, name="sl-window-host", daemon=True)
    thread.start()
    if not ready.wait(START_TIMEOUT) or "port" not in holder:
        raise HostDidNotStart(f"the host did not bind a port on {address} inside {START_TIMEOUT} seconds")
    return Embedded(
        host=host,
        port=int(holder["port"]),
        thread=thread,
        loop=holder["loop"],
        done=holder["done"],
    )


def _server_loop() -> asyncio.AbstractEventLoop:
    """The loop the host serves on.

    `slhost.server.use_selector_loop` says why: the proactor loop of Windows starved a
    socket library in a sibling project. `sl-cli host` sets the policy for its whole
    process. The window cannot do that, because the drawing loop and the client task
    share the process, so it makes the right loop here and changes no policy.
    """
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()


def _drain(loop: asyncio.AbstractEventLoop) -> None:
    """Let the tasks the server left finish, so nothing runs after the loop closes."""
    pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
    for task in pending:
        task.cancel()
    if pending:
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    loop.run_until_complete(loop.shutdown_asyncgens())
