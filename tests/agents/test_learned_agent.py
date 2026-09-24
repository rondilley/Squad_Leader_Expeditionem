"""The learned agent as a computer opponent (FR-51, FR-52).

The wrapper gives a trained PPO snapshot the Agent interface, so it plays in a tournament, a
gate, and a real game. These tests prove four things:

- The command triple of a legal command is a pure mapping, and it needs no torch.
- A snapshot saves with the trainer's own save path and loads back into the agent.
- The agent, in a real decision frame, returns an ID that is one of the frame's legal IDs.
- The default selection is deterministic, so a tournament and a replay agree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from slagents.learned import encoding
from slcli.play import build_engine

SCENARIO = "s01_guards_counterattack"


def first_real_frame(engine):
    """Advance a fresh game to the first frame that has a real choice, not only end_phase."""
    state = engine.new_game(1)
    for _ in range(500):
        frame = engine.legal_commands(state)
        if len(frame.commands) > 1:
            return state, frame
        chosen = frame.commands[0]
        state, _ = engine.apply(state, chosen.command, frame)
    raise AssertionError("no frame with more than one command in the first 500 commands")


def test_command_triple_is_a_pure_mapping_without_torch():
    """The triple mapping is the same one the trainer uses, and it needs no torch."""
    engine = build_engine(SCENARIO)
    hexes = encoding.hex_slots(engine.board)
    state, frame = first_real_frame(engine)
    for legal in frame.commands:
        unit, action, target = encoding.command_triple(legal.command, hexes)
        assert 0 <= unit < len(state.units) + 1
        assert 0 <= action < len(encoding.ACTIONS)
        assert 0 <= target <= len(engine.board)
        again = encoding.command_triple(legal.command, hexes)
        assert (unit, action, target) == again


# ------------------------------------------------------------- torch is needed below
#
# A module-level `importorskip` would skip the whole file, including the pure-mapping test
# above. So the torch tests carry a marker that skips only them when torch is absent, and
# each one imports torch inside itself.

from importlib.util import find_spec  # noqa: E402

needs_torch = pytest.mark.skipif(
    find_spec("torch") is None,
    reason="the learned agent needs torch, the train extra",
)

# A small network, so the test is fast. The shape is in the snapshot, so the agent rebuilds it.
SMALL_NET = dict(channels=4, board_width=16, unit_width=8, hidden=16)


def make_snapshot(engine, tmp_path: Path) -> Path:
    """A snapshot with the trainer's own save path, so the agent loads it the trainer's way."""
    import torch

    from slagents.learned.env import make_env
    from slagents.learned.league import League
    from slagents.learned.nets import NetConfig, Policy

    env = make_env(engine, seed=2)
    torch.manual_seed(0)
    policy = Policy(env.spaces_record, NetConfig(**SMALL_NET))
    league = League()
    return league.take_snapshot(policy, tmp_path, 100, NetConfig(**SMALL_NET))


@needs_torch
def test_a_snapshot_loads_into_the_agent(tmp_path: Path):
    """FR-52: the snapshot the trainer wrote loads back into the deployment wrapper."""
    from slagents.learned.agent import LearnedAgent

    engine = build_engine(SCENARIO)
    path = make_snapshot(engine, tmp_path)
    agent = LearnedAgent(engine, path)
    assert agent.name == "learned"
    assert agent.spaces.cols == engine.board.cols
    assert agent.spaces.rows == engine.board.rows


@needs_torch
def test_the_agent_returns_a_legal_command_id(tmp_path: Path):
    """The core offers the legal commands, and the agent returns the ID of one of them."""
    from slagents.learned.agent import LearnedAgent

    engine = build_engine(SCENARIO)
    path = make_snapshot(engine, tmp_path)
    agent = LearnedAgent(engine, path)
    state, frame = first_real_frame(engine)
    chosen = agent.select(state, frame)
    assert chosen in frame.ids(), "the chosen ID is one of the frame's legal IDs"
    assert frame.by_id(chosen) is not None


@needs_torch
def test_the_default_selection_is_deterministic(tmp_path: Path):
    """A tournament and a replay must give the same command for the same state."""
    from slagents.learned.agent import LearnedAgent

    engine = build_engine(SCENARIO)
    path = make_snapshot(engine, tmp_path)
    agent = LearnedAgent(engine, path)
    state, frame = first_real_frame(engine)
    first = agent.select(state, frame)
    second = agent.select(state, frame)
    assert first == second, "the argmax gives the same ID twice"


@needs_torch
def test_a_seeded_agent_still_returns_a_legal_id(tmp_path: Path):
    """The sampling mode draws over the legal triples, so its ID is legal as well."""
    from slagents.learned.agent import LearnedAgent

    engine = build_engine(SCENARIO)
    path = make_snapshot(engine, tmp_path)
    agent = LearnedAgent(engine, path, seed=7)
    state, frame = first_real_frame(engine)
    chosen = agent.select(state, frame)
    assert chosen in frame.ids()


@needs_torch
def test_a_seeded_agent_is_reproducible(tmp_path: Path):
    """The same seed gives the same draw, so a sampled run replays."""
    from slagents.learned.agent import LearnedAgent

    engine = build_engine(SCENARIO)
    path = make_snapshot(engine, tmp_path)
    state, frame = first_real_frame(engine)
    a = LearnedAgent(engine, path, seed=7)
    b = LearnedAgent(engine, path, seed=7)
    assert a.select(state, frame) == b.select(state, frame)


@needs_torch
def test_an_empty_frame_raises(tmp_path: Path):
    """The engine always offers end_phase, so an empty frame is a defect and it is typed."""
    from slagents.learned.agent import LearnedAgent, NoLegalCommand
    from slcore.frame import DecisionFrame

    engine = build_engine(SCENARIO)
    path = make_snapshot(engine, tmp_path)
    agent = LearnedAgent(engine, path)
    empty = DecisionFrame("f", 0, "phase", "sub", 1, ())
    state = engine.new_game(1)
    with pytest.raises(NoLegalCommand):
        agent.select(state, empty)


@needs_torch
def test_make_agent_builds_the_learned_agent(tmp_path: Path):
    """slcli.play.make_agent parses the learned: prefix and builds the wrapper."""
    from slagents.learned.agent import LearnedAgent
    from slcli.play import make_agent

    engine = build_engine(SCENARIO)
    path = make_snapshot(engine, tmp_path)
    agent = make_agent(f"learned:{path}", engine, seed=1, player=0)
    assert isinstance(agent, LearnedAgent)
    assert agent.name == "learned"


@needs_torch
def test_a_snapshot_of_the_wrong_board_size_raises(tmp_path: Path):
    """A snapshot trained on another board must not load, because its heads do not match."""
    import torch

    from slagents.learned.agent import LearnedAgent, SnapshotShapeError
    from slagents.learned.env import make_env
    from slagents.learned.nets import NetConfig, Policy

    engine = build_engine(SCENARIO)
    env = make_env(engine, seed=2)
    policy = Policy(env.spaces_record, NetConfig(**SMALL_NET))
    # Save with a spaces record of a board one column wider than the engine.
    path = tmp_path / "wrong.pt"
    torch.save(
        {
            "step": 1,
            "state_dict": policy.state_dict(),
            "net": SMALL_NET,
            "spaces": {
                "units": policy.spaces.units,
                "actions": policy.spaces.actions,
                "targets": policy.spaces.targets,
                "cols": policy.spaces.cols + 1,
                "rows": policy.spaces.rows,
            },
        },
        path,
    )
    with pytest.raises((SnapshotShapeError, RuntimeError)):
        LearnedAgent(engine, path)


def test_the_batched_scores_are_the_composed_log_probabilities_of_each_command():
    """Each score is the sum of the four heads' log probabilities under the same masks."""
    import numpy as np
    import torch

    from slagents.learned import encoding
    from slagents.learned.agent import LearnedAgent
    from slagents.learned.nets import NetConfig, Policy
    from slcli.play import build_engine

    engine = build_engine("s01_guards_counterattack")
    state = engine.new_game(21)
    frame = engine.legal_commands(state)
    spaces = encoding.spaces_for(engine.board, len(state.units))
    torch.manual_seed(3)
    policy = Policy(spaces, NetConfig(channels=4, board_width=32, unit_width=16, hidden=32))
    agent = LearnedAgent.from_policy(engine, policy)
    groups = encoding.group_commands(frame, agent.hexes)
    player = frame.player
    board = torch.from_numpy(encoding.board_tensor(engine.board, state, engine.types, player, spaces, agent.objectives)).unsqueeze(0)
    units = torch.from_numpy(encoding.unit_tensor(state, engine.types, player, spaces, engine.board, sorted({u for u, _, _, _ in groups}))).unsqueeze(0)
    scalars = torch.from_numpy(encoding.scalar_vector(state, frame, player)).unsqueeze(0)
    with torch.no_grad():
        trunk, embeddings = policy.encode(board, units, scalars)
        scores = agent._scores(trunk, embeddings, groups, torch, torch.device("cpu"))
    assert set(scores) == set(groups)
    unit_mask, action_mask = encoding.masks_from(groups, spaces)
    for quad in sorted(groups)[:6]:
        u, a, t, o = quad
        target_mask = encoding.target_mask_for(groups, spaces, u, a)
        option_mask = encoding.option_mask_for(groups, spaces, u, a, t)
        with torch.no_grad():
            log_prob, _, _ = policy.evaluate(
                board, units, scalars,
                torch.from_numpy(unit_mask.astype(np.float32)).unsqueeze(0),
                torch.from_numpy(action_mask.astype(np.float32)).unsqueeze(0),
                torch.from_numpy(target_mask.astype(np.float32)).unsqueeze(0),
                torch.from_numpy(option_mask.astype(np.float32)).unsqueeze(0),
                torch.tensor([u]), torch.tensor([a]), torch.tensor([t]), torch.tensor([o]),
            )
        assert scores[quad] == pytest.approx(float(log_prob.item()), abs=1e-4)
