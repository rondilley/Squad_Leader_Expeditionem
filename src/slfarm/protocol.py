"""The protocol of the game farm: one JSON object on each line of a TCP stream.

The server speaks first:

    server: {"type": "challenge", "protocol": 1, "nonce": <hex>, "code": <hex>, "slots": N}
    client: {"type": "auth", "mac": <HMAC-SHA256 of the nonce with the key, hex>}
    server: {"type": "ready"}                       or {"type": "error", "error": ...} and close

Then the client sends jobs, and the server answers each one, in any order:

    client: {"type": "job", "id": K, "scenario": "s04_armor_probe", "seed": 7, "agents": ["v7", "v6"]}
    client: {"type": "job", "id": K, "scenario_doc": {...}, "seed": 7, "agents": ["v7", "v6"]}
    server: {"type": "result", "id": K, "outcome": {...}}
    server: {"type": "refused", "id": K, "error": ...}
    client: {"type": "ping"}  ->  server: {"type": "pong", "slots": N, "busy": B, "envs": E}

A connection can instead hold one PPO environment (`slfarm.envwire`) for its life:

    client: {"type": "env_open", "scenario": ..., "index": I, "seed": S, "max_commands": M}
    server: {"type": "env_ready"}               or {"type": "env_error", "error": ...} and close
    client: {"type": "env", "command": ["reset", ...] | ["act", [a, b, c, d]] | ["stop"]}
    server: {"type": "env_decision", "observation": {...}, "legal": [...], ...}

A job is data. The server checks the scenario against its own list (or a scenario
document, a variant under test, with the checks of a scenario file), the seed against the
range of a seed, and each agent name against the names of the scripted agents. A learned
agent reads a file and a model agent uses the network and a key, so the farm refuses both.
The server runs no code that the network sends.

The key is the first line of a `*.key.txt` file, which git does not record, and it never
goes on the wire: the client proves it with an HMAC of a nonce the server picks for the
connection. The code hash is a hash of the source tree of the host. A client refuses a host
whose code is not the same as its own, because a game is its seed only on the same code.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from pathlib import Path
from typing import Any

PROTOCOL = 1
DEFAULT_PORT = 5160
# The longest line either side reads. A job is about a hundred bytes, a result about a
# kilobyte, and a PPO decision about 50 kilobytes, so a longer line is a fault or an attack,
# and the connection closes.
MAX_LINE = 4 * 1024 * 1024
AUTH_TIMEOUT_SECONDS = 10.0
KEY_MIN_LENGTH = 32
SEED_LIMIT = 2**63
# The scripted agents, with a nation and a parameter set: v7, v7:german, v7[a=1,b=2].
AGENT_PATTERN = re.compile(r"^(random|v[0-7](:[a-z]+)?(\[[a-z0-9_=,\-]*\])?)$")
SCENARIO_PATTERN = re.compile(r"^[a-z0-9_]{1,64}$")


class FarmError(Exception):
    """A fault of the farm: a host, a connection, or a job."""


class FarmKeyError(FarmError):
    """The key file is missing, empty, or too short."""


class FarmAuthError(FarmError):
    """The other side did not prove the key."""


class FarmVersionError(FarmError):
    """The host runs other code, or another protocol."""


class FarmProtocolError(FarmError):
    """A message that is not one of the protocol."""


class JobRefused(FarmError):
    """A job that the server does not play."""


def read_key(path: str | Path) -> bytes:
    """The key: the first line of the file, at least `KEY_MIN_LENGTH` characters."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise FarmKeyError(f"cannot read the farm key file {path}: {exc.strerror}") from exc
    lines = text.splitlines()
    key = lines[0].strip() if lines else ""
    if len(key) < KEY_MIN_LENGTH:
        raise FarmKeyError(f"the farm key in {path} has {len(key)} characters; it needs {KEY_MIN_LENGTH} or more")
    return key.encode("utf-8")


def new_key() -> str:
    return secrets.token_hex(32)


def new_nonce() -> str:
    return secrets.token_hex(16)


def mac_of(key: bytes, nonce: str) -> str:
    return hmac.new(key, nonce.encode("ascii"), hashlib.sha256).hexdigest()


def mac_matches(key: bytes, nonce: str, mac: Any) -> bool:
    return isinstance(mac, str) and hmac.compare_digest(mac_of(key, nonce), mac)


def code_hash(root: Path | None = None) -> str:
    """A hash of each source and data file below `src/`, with its path.

    The line ends are read as LF, so a checkout on Windows and one on Ubuntu give the same
    hash. The compiled files and the package metadata are not in it.
    """
    base = root or Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix not in (".py", ".json"):
            continue
        rel = path.relative_to(base).as_posix()
        if "__pycache__" in rel or ".egg-info" in rel:
            continue
        digest.update(rel.encode("utf-8") + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


def encode(message: dict[str, Any]) -> bytes:
    return (json.dumps(message, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def decode(line: bytes) -> dict[str, Any]:
    if len(line) > MAX_LINE:
        raise FarmProtocolError(f"a line of {len(line)} bytes is longer than {MAX_LINE}")
    try:
        message = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FarmProtocolError(f"a line that is not JSON: {exc}") from exc
    if not isinstance(message, dict) or not isinstance(message.get("type"), str):
        raise FarmProtocolError("a message is a JSON object with a type")
    return message


def check_job(message: dict[str, Any], scenarios: frozenset[str]) -> tuple[int, tuple[Any, int, str, str]]:
    """The id and the game of a job message: (scenario, seed, first agent, second agent).

    The scenario is the id of a scenario of this host, or the document of a variant
    (`scenario_doc`), which must pass the checks of a scenario file."""
    job_id = message.get("id")
    if not isinstance(job_id, int) or isinstance(job_id, bool) or job_id < 0:
        raise FarmProtocolError("a job has a whole number id of 0 or more")
    scenario = check_scenario(message, scenarios, f"job {job_id}")
    seed = message.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < SEED_LIMIT:
        raise JobRefused(f"job {job_id}: the seed {seed!r} is not a whole number from 0 to 2**63")
    agents = message.get("agents")
    if not isinstance(agents, list) or len(agents) != 2:
        raise JobRefused(f"job {job_id}: a job names two agents")
    for name in agents:
        if not isinstance(name, str) or not AGENT_PATTERN.match(name):
            raise JobRefused(f"job {job_id}: the farm plays the scripted agents only, not {name!r}")
    return job_id, (scenario, seed, agents[0], agents[1])


def check_scenario(message: dict[str, Any], scenarios: frozenset[str], label: str) -> Any:
    """The scenario of a message: the id of a scenario of this host, or a document
    (`scenario_doc`) that passes the checks of a scenario file."""
    if "scenario_doc" in message:
        scenario = message["scenario_doc"]
        from sldata.loaders import DataError, scenario_from_document

        try:
            scenario_from_document(scenario, f"{label}: the scenario document")
        except DataError as exc:
            raise JobRefused(str(exc)) from exc
        return scenario
    scenario = message.get("scenario")
    if not isinstance(scenario, str) or not SCENARIO_PATTERN.match(scenario) or scenario not in scenarios:
        raise JobRefused(f"{label}: the scenario {scenario!r} is not a scenario of this host")
    return scenario


def check_env_open(message: dict[str, Any], scenarios: frozenset[str]) -> tuple[Any, int, int, int]:
    """The scenario, the worker index, the seed, and the command limit of an `env_open`."""
    scenario = check_scenario(message, scenarios, "env_open")
    values = [message.get(name) for name in ("index", "seed", "max_commands")]
    if not all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v < SEED_LIMIT for v in values):
        raise FarmProtocolError("env_open has a whole number index, seed, and max_commands")
    if not 0 < values[2] <= 1_000_000:
        raise JobRefused("the command limit of an environment is from 1 to 1,000,000")
    return scenario, values[0], values[1], values[2]


def check_agents_for_farm(names: list[str]) -> None:
    """The client test of the same rule, before a run sends its first job."""
    for name in names:
        if not AGENT_PATTERN.match(name):
            raise JobRefused(
                f"the farm plays the scripted agents only, and {name!r} is not one: a learned agent "
                "reads a snapshot file and a model agent needs the network; play it with --workers"
            )
