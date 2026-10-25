"""The PPO environment messages of the farm, as JSON (2026-10-14).

A remote PPO worker is the loop of `slagents.learned.workers.worker_main` on a farm host. The
trainer talks to it with the tuples of that loop (`reset`, `act`, `stop`), and the loop
answers with a `Decision`. On the network the two are JSON. The arrays of an observation go
as base64 with a declared dtype and shape, because pickle runs code and the farm runs no
code from the network. Each side checks what it reads: the command of the trainer on the
host, and the decision of the host on the workstation.
"""

from __future__ import annotations

import base64
import math
from typing import Any

from slfarm import protocol as p

# The dtypes an observation uses. An array of another dtype is a fault of the other side.
DTYPES = ("float32", "int8", "int64", "bool")
MAX_KEYS = 100_000


def encode_array(array: Any) -> dict[str, Any]:
    import numpy as np

    data = np.ascontiguousarray(array)
    if str(data.dtype) not in DTYPES:
        raise p.FarmProtocolError(f"an array of dtype {data.dtype} is not one of {DTYPES}")
    return {"dtype": str(data.dtype), "shape": list(data.shape), "data": base64.b64encode(data.tobytes()).decode("ascii")}


def decode_array(message: Any) -> Any:
    import numpy as np

    if not isinstance(message, dict):
        raise p.FarmProtocolError("an array is an object with dtype, shape, and data")
    dtype, shape, data = message.get("dtype"), message.get("shape"), message.get("data")
    if dtype not in DTYPES:
        raise p.FarmProtocolError(f"an array of dtype {dtype!r} is not one of {DTYPES}")
    if not isinstance(shape, list) or not all(isinstance(n, int) and not isinstance(n, bool) and 0 <= n < 1_000_000 for n in shape):
        raise p.FarmProtocolError("the shape of an array is a list of whole numbers")
    try:
        raw = base64.b64decode(str(data), validate=True)
    except ValueError as exc:
        raise p.FarmProtocolError(f"the data of an array is not base64: {exc}") from exc
    if len(raw) != math.prod(shape) * np.dtype(dtype).itemsize:
        raise p.FarmProtocolError("the data of an array does not have the size of its shape")
    return np.frombuffer(raw, dtype=dtype).reshape(shape).copy()


def _keys(value: Any) -> list[tuple[int, int, int, int]]:
    if not isinstance(value, list) or len(value) > MAX_KEYS:
        raise p.FarmProtocolError("the legal keys are a list")
    return [_key(item) for item in value]


def _key(value: Any) -> tuple[int, int, int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 4 or not all(isinstance(n, int) and not isinstance(n, bool) for n in value):
        raise p.FarmProtocolError("a command key is four whole numbers")
    return (value[0], value[1], value[2], value[3])


def encode_decision(decision: Any) -> dict[str, Any]:
    return {
        "type": "env_decision",
        "observation": {name: encode_array(array) for name, array in decision.observation.items()},
        "legal": [list(key) for key in decision.legal],
        "reward_delta": float(decision.reward_delta),
        "ended": bool(decision.ended),
        "result": float(decision.result),
        "work_seconds": float(decision.work_seconds),
    }


def decode_decision(message: dict[str, Any]) -> Any:
    from slagents.learned.workers import Decision

    observation = message.get("observation")
    if not isinstance(observation, dict) or not all(isinstance(name, str) for name in observation):
        raise p.FarmProtocolError("an observation is an object of arrays")
    numbers = [message.get("reward_delta"), message.get("result"), message.get("work_seconds")]
    if not all(isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) for n in numbers):
        raise p.FarmProtocolError("the reward, the result, and the work time of a decision are numbers")
    if not isinstance(message.get("ended"), bool):
        raise p.FarmProtocolError("the end mark of a decision is true or false")
    return Decision(
        {name: decode_array(array) for name, array in observation.items()},
        _keys(message.get("legal")),
        float(numbers[0]),
        message["ended"],
        float(numbers[1]),
        float(numbers[2]),
    )


def encode_command(command: tuple) -> list[Any]:
    """A command of the trainer: ("reset", spec, learner, seed, guide), ("act", key), ("stop",)."""
    kind = command[0]
    if kind == "reset":
        _, spec, learner, seed, guide = command
        return ["reset", list(spec), int(learner), int(seed), None if guide is None else [str(guide[0]), int(guide[1])]]
    if kind == "act":
        return ["act", [int(x) for x in command[1]]]
    if kind == "stop":
        return ["stop"]
    raise p.FarmProtocolError(f"a command of type {kind!r} is not one of the trainer")


def check_command(value: Any) -> tuple:
    """The command as the worker loop takes it, with the checks of the host.

    The opponent of a game is random or a scripted agent. A snapshot opponent reads a file
    of the workstation, so the farm refuses it.
    """
    if not isinstance(value, list) or not value or not isinstance(value[0], str):
        raise p.FarmProtocolError("a command is a list with its type first")
    kind = value[0]
    if kind == "stop" and len(value) == 1:
        return ("stop",)
    if kind == "act" and len(value) == 2:
        return ("act", _key(value[1]))
    if kind == "reset" and len(value) == 5:
        _, spec, learner, seed, guide = value
        if spec == ["random"]:
            member: tuple[str, ...] = ("random",)
        elif isinstance(spec, list) and len(spec) == 2 and spec[0] == "scripted" and isinstance(spec[1], str) and p.AGENT_PATTERN.match(spec[1]):
            member = ("scripted", spec[1])
        else:
            raise p.JobRefused(f"the farm plays random and scripted opponents only, not {spec!r}")
        if learner not in (0, 1) or isinstance(learner, bool):
            raise p.FarmProtocolError("the learner of a game is player 0 or player 1")
        if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < p.SEED_LIMIT:
            raise p.FarmProtocolError("the seed of a game is a whole number from 0 to 2**63")
        if guide is not None:
            if not (isinstance(guide, list) and len(guide) == 2 and isinstance(guide[0], str) and p.AGENT_PATTERN.match(guide[0])
                    and isinstance(guide[1], int) and not isinstance(guide[1], bool) and 0 <= guide[1] <= 1000):
                raise p.JobRefused(f"the guide of a game is a scripted agent and a count of turns, not {guide!r}")
            guide = (guide[0], guide[1])
        return ("reset", member, learner, seed, guide)
    raise p.FarmProtocolError(f"the command {kind!r} is not one of the trainer")
