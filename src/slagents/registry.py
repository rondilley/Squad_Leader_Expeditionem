"""The agents by name and the engine of a scenario by name (FR-43, FR-44).

The command line, the host, the trainer, the worker processes, and the shape study each
build an engine and agents from text. That construction is a library concern, so it
lives here and not in `slcli`. A library package imports this module, and no library
package imports `slcli` (the layering test in `tests/arch/`).

An agent name is an exact name (`v1`) or a prefix with a part that follows it
(`v7:german`, `model:local+openai`, `learned:<snapshot>`). `AGENT_NAMES` holds the exact
names and `AGENT_PREFIXES` the prefixes, each with its builder. `make_agent` reads the
exact table first and then the prefixes in their order.
"""

from __future__ import annotations

from typing import Any, Callable

from slagents.base import Agent, RandomAgent
from slagents.scripted.v0 import ScriptedV0
from slagents.scripted.v1 import ScriptedV1
from slagents.scripted.v2 import ScriptedV2
from slagents.scripted.v3 import ScriptedV3
from slagents.scripted.v4 import ScriptedV4, profile_for
from slagents.scripted.v5 import ScriptedV5, profile_for as profile_for_v5
from slagents.scripted.v6 import ScriptedV6, profile_for as profile_for_v6
from slagents.scripted.v7 import ScriptedV7, parameters_from_text as parameters_v7
from slboards.reference import source_of
from slcore.engine import Engine
from sldata.loaders import (
    DataError,
    board_and_parameters,
    load_all_counters,
    load_board,
    load_hexsides,
    load_scenario,
    load_scenario_file,
    load_tables,
    load_terrain,
    scenario_from_document,
)

LEARNED_PREFIX = "learned:"
RANDOM_PREFIX = "random:"
# A scenario that is a JSON file and not a file of `sldata/scenarios`: `file:<path>`, for a
# variant under test (2026-10-14).
FILE_PREFIX = "file:"
MAX_WORKERS = 64

AgentBuilder = Callable[[str, Engine, int, int], Agent]


class LearnedNotInstalled(Exception):
    """The learned agent needs torch, which is the `train` extra, and it is not installed."""

    def __init__(self) -> None:
        super().__init__(
            "the learned agent needs torch. Install it with: pip install -e \".[train]\""
        )


def limit_workers(workers: int) -> int:
    """The count, when it is from 1 to `MAX_WORKERS`.

    A command that starts one process for each worker has no other limit. A large count
    forks until the machine stops. 64 is enough for the benches and the gauntlets on the
    owner's machines, and each pool refuses a larger count.
    """
    if workers < 1 or workers > MAX_WORKERS:
        raise ValueError(f"workers must be from 1 to {MAX_WORKERS}, not {workers}")
    return workers


def build_engine(scenario_name: str | dict[str, Any], board_name: str | None = None) -> Engine:
    engine, _ = build_engine_with_record(scenario_name, board_name)
    return engine


def random_scenario(name: str):
    """A scenario that the random construction of Game Set IV builds from a seed (FR-17).

    `random:500` is a scenario the same way `s01_guards_counterattack` is one. It has no
    file, because the seed is the whole record: the draws, the two forces, and the board
    all come from it.
    """
    from slcampaign.build import build_scenario
    from slcampaign.generator import draw_scenario
    from slcampaign.run import counter_types, point_values

    text = name[len(RANDOM_PREFIX) :]
    try:
        seed = int(text)
    except ValueError as exc:
        raise DataError(f"a random scenario needs a seed, and {text!r} is not one") from exc
    types = counter_types()
    draw, defending, attacking = draw_scenario(seed, types, point_values(types))
    return build_scenario(seed, draw, defending, attacking, types)


def build_engine_with_record(
    scenario_name: str | dict[str, Any], board_name: str | None = None
) -> tuple[Engine, dict[str, Any]]:
    """The engine and the record of the board it plays on (FR-25).

    The record goes in the run artifact, so that a later session builds the same board
    from the same parameters. A board from the reference directory carries its source
    tag and no parameters, because the project does not ship that layout (DR-06).

    A name that starts with `random:` is a scenario of Game Set IV, built from the seed
    that follows the prefix, and not a file in `sldata/scenarios`. A name that starts with
    `file:` is a scenario file at that path, and a dict is the document of a scenario.
    """
    if isinstance(scenario_name, dict):
        # The document of a scenario variant that the game farm got from a client.
        scenario = scenario_from_document(scenario_name)
    elif scenario_name.startswith(FILE_PREFIX):
        scenario = load_scenario_file(scenario_name[len(FILE_PREFIX) :])
    elif scenario_name.startswith(RANDOM_PREFIX):
        scenario = random_scenario(scenario_name)
    else:
        scenario = load_scenario(scenario_name)
    terrain = load_terrain()
    if board_name:
        board = load_board(board_name, terrain)
        params = None
    else:
        board, params = board_and_parameters(scenario, terrain)
    record: dict[str, Any] = {
        "board": board.name,
        "board_source": source_of(board),
        "board_columns": list(scenario.board_columns) if scenario.board_columns else None,
        "generator": params.to_dict() if params is not None else None,
    }
    engine = Engine(scenario, board, terrain, load_hexsides(), load_all_counters(), load_tables())
    return engine, record


def make_learned_agent(snapshot_path: str, engine: Engine, seed: int, player: int) -> Agent:
    """A trained PPO snapshot as a computer opponent (FR-51, FR-52).

    The snapshot is a file that `sl-cli train` wrote. Torch is the `train` extra, so the
    import is late and its absence gives the typed error of this boundary, the way the
    desktop and finetune commands do.
    """
    if not snapshot_path:
        raise ValueError("a learned agent needs a snapshot path, as learned:<path>")
    try:
        import torch  # noqa: F401  the boundary of an optional dependency
    except ImportError as exc:
        raise LearnedNotInstalled() from exc
    from slagents.learned.agent import LearnedAgent

    return LearnedAgent(engine, snapshot_path, seed=None)


def make_model_agent(providers: str, engine: Engine, seed: int, player: int, tuned: bool = False) -> Agent:
    """A model agent (FR-45). The name is a sequence, so `model:local+openai` fails over.

    A name with a star is a pool: `model:local*` is each provider whose name starts with
    `local`, and the seed of the game picks the first one, so the games of a gauntlet
    spread across the hosts of the pool. The tuned family is the same harness with the
    constraint of FR-62 on: the provider holds the model to the schema, whose command
    field is the enum of the legal identities.
    """
    from slagents.prompted.harness import PromptedAgent
    from slagents.prompted.providers import make_provider, pool_names
    from slagents.prompted.router import Router

    names = [name for part in providers.split("+") if part for name in pool_names(part, seed=seed)]
    if not names:
        raise ValueError("a model agent needs one provider name or more, as model:local+openai")
    clients = [make_provider(name) for name in names]
    client = clients[0] if len(clients) == 1 else Router(clients)
    agent = PromptedAgent(engine, player, client, ScriptedV1(engine, player), constrained=tuned)
    if tuned:
        agent.name = "tuned"
    return agent


def unknown_agent(kind: str) -> ValueError:
    """The error for a name that no table entry accepts."""
    return ValueError(
        f"unknown agent kind {kind!r}; use random, v0, v1, v2, v3, v4, v4:<nation>, v5, v5:<nation>, v6, v6:<nation>, v7, v7:<nation>, "
        "model:<providers>, tuned:<providers>, or learned:<snapshot>"
    )


def _after_colon(kind: str) -> str:
    return kind.split(":", 1)[1]


def _v7_nation(kind: str, engine: Engine, seed: int, player: int) -> Agent:
    # A nation record, with a few values of its own in brackets when a study wants
    # them. The role of the side picks the record: a side with a positional victory
    # condition attacks, and the other side defends (`side_defends`).
    from slagents.scripted.v7 import parameters_of_name, side_defends

    return ScriptedV7(engine, player, parameters_of_name(kind, side_defends(engine, player)))


def _v7_parameters(kind: str, engine: Engine, seed: int, player: int) -> Agent:
    # The named parameters of FR-44 on the command line, as v7[loss_scale=8,route_loss=12],
    # so a parameter study runs through the gauntlet with no code change.
    if not kind.endswith("]"):
        raise unknown_agent(kind)
    return ScriptedV7(engine, player, parameters_v7(kind[3:-1]))


# The exact names. The builder gets the name, the engine, the seed of the game, and the player.
AGENT_NAMES: dict[str, AgentBuilder] = {
    "random": lambda kind, engine, seed, player: RandomAgent(seed, player),
    "v0": lambda kind, engine, seed, player: ScriptedV0(engine, player),
    "v1": lambda kind, engine, seed, player: ScriptedV1(engine, player),
    "v2": lambda kind, engine, seed, player: ScriptedV2(engine, player),
    "v3": lambda kind, engine, seed, player: ScriptedV3(engine, player),
    "v4": lambda kind, engine, seed, player: ScriptedV4(engine, player),
    "v5": lambda kind, engine, seed, player: ScriptedV5(engine, player),
    "v6": lambda kind, engine, seed, player: ScriptedV6(engine, player),
    "v7": lambda kind, engine, seed, player: ScriptedV7(engine, player),
}

# The prefixes, in the order `make_agent` reads them. The builder gets the full name.
AGENT_PREFIXES: tuple[tuple[str, AgentBuilder], ...] = (
    ("v4:", lambda kind, engine, seed, player: ScriptedV4(engine, player, profile_for(_after_colon(kind)))),
    ("v5:", lambda kind, engine, seed, player: ScriptedV5(engine, player, profile_for_v5(_after_colon(kind)))),
    ("v6:", lambda kind, engine, seed, player: ScriptedV6(engine, player, profile_for_v6(_after_colon(kind)))),
    ("v7:", _v7_nation),
    ("v7[", _v7_parameters),
    ("model:", lambda kind, engine, seed, player: make_model_agent(_after_colon(kind), engine, seed, player)),
    ("tuned:", lambda kind, engine, seed, player: make_model_agent(_after_colon(kind), engine, seed, player, tuned=True)),
    (LEARNED_PREFIX, lambda kind, engine, seed, player: make_learned_agent(kind[len(LEARNED_PREFIX) :], engine, seed, player)),
)


def make_agent(kind: str, engine: Engine, seed: int, player: int) -> Agent:
    """The agent that `kind` names, for `player` on `engine`, with the seed of the game."""
    builder = AGENT_NAMES.get(kind)
    if builder is not None:
        return builder(kind, engine, seed, player)
    for prefix, builder in AGENT_PREFIXES:
        if kind.startswith(prefix):
            return builder(kind, engine, seed, player)
    raise unknown_agent(kind)
