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


def _movement_with_weapons(engine, seed: int):
    """A real scenario 2 state in a Movement Phase whose frame offers a pickup or a drop."""
    from slagents.base import decide
    from slcli.play import make_agent

    agents = (make_agent("v1", engine, seed, 0), make_agent("v1", engine, seed, 1))
    state = engine.new_game(seed)
    for _ in range(20000):
        frame = engine.legal_commands(state)
        if state.phase == "movement" and sum(c.command.action in ("pickup", "drop") for c in frame.commands) >= 2:
            return state
        state, _ = engine.apply(state, frame.by_id(decide(agents[state.active], state, frame)).command, frame)
    raise AssertionError("no Movement Phase with two weapon commands")


def _weapon_commands_in_phase(engine, state, agent, limit: int) -> tuple[int, int, bool]:
    """The pickups and drops the agent plays before its phase ends, the weapons, and the end."""
    from slagents.base import decide

    start = (state.turn, state.phase, state.active)
    weapons = {u.id for u in state.units if u.kind == "sw" and u.player == state.active and not u.eliminated}
    count = 0
    for _ in range(limit):
        if (state.turn, state.phase, state.active) != start or state.game_over:
            return count, len(weapons), True
        frame = engine.legal_commands(state)
        legal = frame.by_id(decide(agent, state, frame))
        if legal.command.action in ("pickup", "drop"):
            count += 1
        state, _ = engine.apply(state, legal.command, frame)
    return count, len(weapons), False


@needs_torch
def test_a_policy_that_likes_weapons_does_not_walk_through_the_holders():
    """A pickup and a drop are free (rule 5.7), so the guard against a repeat alone let a
    policy hand the weapons around for thousands of commands, each with a new set of
    holders (the scenario 2 net, 2026-10-12). The agent puts a second pickup or drop of a
    weapon in the same phase after each other command, so the phase ends with at most two
    such commands for each weapon.
    """
    import torch

    from slagents.learned.agent import WEAPON_ACTIONS, LearnedAgent
    from slagents.learned.nets import NetConfig, Policy

    engine = build_engine("s02_tractor_works")
    state = _movement_with_weapons(engine, 2)
    spaces = encoding.spaces_for(engine.board, len(state.units))
    torch.manual_seed(0)
    policy = Policy(spaces, NetConfig(**SMALL_NET))

    class WeaponFirst(LearnedAgent):
        """The net's preference of the failed games: each pickup and drop over the rest."""

        def _by_score(self, scores, groups):
            ordered = LearnedAgent._by_score(scores, groups)
            return [c for c in ordered if c.command.action in WEAPON_ACTIONS] + [
                c for c in ordered if c.command.action not in WEAPON_ACTIONS
            ]

    fixed = WeaponFirst.from_policy(engine, policy)
    count, weapons, ended = _weapon_commands_in_phase(engine, state, fixed, 2000)
    assert ended, "the phase ends"
    assert 0 < count <= 2 * weapons, (count, weapons)

    class GuardOnly(WeaponFirst):
        """The agent before the fix: the guard against an exact repeat only."""

        def _weapons_handled_last(self, state, ordered, player):
            return ordered

    walked, weapons, _ended = _weapon_commands_in_phase(engine, state, GuardOnly.from_policy(engine, policy), 400)
    assert walked > 2 * weapons, (walked, weapons)


def _movement_with(engine, seed: int, agent_name: str, action: str, count: int):
    """A real state in a Movement Phase whose frame offers `count` commands of `action`."""
    from slagents.base import decide
    from slcli.play import make_agent

    agents = (make_agent(agent_name, engine, seed, 0), make_agent(agent_name, engine, seed, 1))
    state = engine.new_game(seed)
    for _ in range(20000):
        assert not state.game_over, f"the game ended before a Movement Phase with {action}"
        frame = engine.legal_commands(state)
        if state.phase == "movement" and sum(c.command.action == action for c in frame.commands) >= count:
            return state, frame
        state, _ = engine.apply(state, frame.by_id(decide(agents[state.active], state, frame)).command, frame)
    raise AssertionError(f"no Movement Phase with {count} commands of {action}")


def test_the_choice_is_the_action_with_the_most_probability_first():
    """The policy divides the probability of a move between many units and hexes, and the
    probability of end_phase stays on one command. The joint argmax then ends the phase
    with no move (s04, 2026-10-13). The agent sums the probability of each action over its
    legal commands, and plays the best command of the action with the highest sum.
    """
    import math

    from slagents.learned.agent import LearnedAgent

    engine = build_engine("s04_armor_probe")
    state, frame = _movement_with(engine, 2, "random", "move", 4)
    groups = encoding.group_commands(frame, encoding.hex_slots(engine.board))
    moves = [k for k, c in groups.items() if c.command.action == "move"]
    others = [k for k, c in groups.items() if c.command.action not in ("move", "end_phase")]
    end = next(k for k, c in groups.items() if c.command.action == "end_phase")
    scores = {k: math.log(0.6 / len(moves)) for k in moves}
    scores[moves[-1]] = math.log(0.6 / len(moves) * 1.5)
    scores.update({k: math.log(0.1 / max(1, len(others))) for k in others})
    scores[end] = math.log(0.3)
    assert max(scores, key=scores.get) == end, "the joint argmax is end_phase"
    ordered = LearnedAgent._by_score(scores, groups)
    assert ordered[0] is groups[moves[-1]], "the best move comes first"
    assert {c.command.action for c in ordered[: len(moves)]} == {"move"}
    assert ordered[len(moves)] is groups[end]


def _prep_fire_with(engine, seed: int, agent_name: str, count: int):
    """A real state in a Prep Fire Phase whose frame offers `count` commands or more that are not end_phase."""
    from slagents.base import decide
    from slcli.play import make_agent

    agents = (make_agent(agent_name, engine, seed, 0), make_agent(agent_name, engine, seed, 1))
    state = engine.new_game(seed)
    for _ in range(20000):
        assert not state.game_over, "the game ended before a Prep Fire Phase with fire"
        frame = engine.legal_commands(state)
        if frame.phase == "prep_fire" and sum(c.command.action != "end_phase" for c in frame.commands) >= count:
            return state, frame
        state, _ = engine.apply(state, frame.by_id(decide(agents[state.active], state, frame)).command, frame)
    raise AssertionError("no Prep Fire Phase with fire")


def test_the_prep_fire_choice_is_the_highest_joint_score():
    """In the Prep Fire Phase each unit that can fire adds to the sum of a fire action, and
    the end of the phase stays on one command. The L05 clone gave the end of the phase 0.31
    where the teacher ended it in 77 percent, so the action first fired, and the units that
    fired did not move (2026-10-27). In that phase the agent plays the highest joint score.
    """
    import math

    from slagents.learned.agent import JOINT_SCORE_PHASES, LearnedAgent

    assert "prep_fire" in JOINT_SCORE_PHASES and "movement" not in JOINT_SCORE_PHASES
    engine = build_engine("s01_guards_counterattack")
    state, frame = _prep_fire_with(engine, 1, "random", 3)
    groups = encoding.group_commands(frame, encoding.hex_slots(engine.board))
    end = next(k for k, c in groups.items() if c.command.action == "end_phase")
    fires = [k for k, c in groups.items() if c.command.action != "end_phase"]
    same = [k for k in fires if k[1] == fires[0][1]]
    assert len(same) >= 2, "one fire action has two commands or more"
    scores = {k: math.log(0.2 / len(fires)) for k in fires}
    scores.update({k: math.log(0.5 / len(same)) for k in same})
    scores[end] = math.log(0.3)
    assert LearnedAgent._by_score(scores, groups)[0] is not groups[end], "the action first fires"
    assert LearnedAgent._by_joint_score(scores, groups)[0] is groups[end], "the joint score ends the phase"


def test_a_route_and_a_stack_route_share_one_sum():
    """Each unit has single routes and only a stack has stack routes, so with two sums the
    single route won each time, and the L05 leaders went forward alone (2026-10-27). The
    two actions share one sum, and the best command of the two comes first.
    """
    import math

    from slagents.learned import routes
    from slagents.learned.agent import LearnedAgent

    engine = build_engine("s01_guards_counterattack")
    state, frame = _movement_with(engine, 1, "v6", "stack_move", 1)
    hexes = encoding.hex_slots(engine.board)
    table = routes.route_table(engine, state, frame, hexes, routes.PhaseMemory())
    groups = routes.with_routes(encoding.group_commands(frame, hexes), dict(table))
    route = encoding.ACTION_INDEX["route"]
    stack = encoding.ACTION_INDEX["stack_route"]
    singles = [k for k in groups if k[1] == route]
    stacks = [k for k in groups if k[1] == stack]
    others = [k for k in groups if k[1] not in (route, stack)]
    assert singles and stacks and others
    scores = {k: math.log(0.3 / len(singles)) for k in singles}
    scores.update({k: math.log(0.1 / len(stacks)) for k in stacks})
    scores[stacks[0]] = math.log(0.25)
    scores.update({k: math.log(0.35 / len(others)) for k in others})
    ordered = LearnedAgent._by_score(scores, groups)
    assert ordered[0] is groups[stacks[0]], "the best stack route comes first, by the sum of the two actions"


@needs_torch
def test_a_policy_that_likes_to_ride_does_not_board_and_debark_without_end():
    """The core lets a unit that debarked board again, so a policy that likes a board and a
    debark got on a tank and off it 250 times in one phase (2026-10-13). The agent puts a
    second board or debark of one unit in a phase after each other command. Since PR-55 the
    core offers one board or debark of a unit in each Movement Phase, so the phase ends with
    one ride of each unit at most.
    """
    import torch

    from slagents.base import decide
    from slagents.learned.agent import RIDE_ACTIONS, LearnedAgent
    from slagents.learned.nets import NetConfig, Policy

    engine = build_engine("s04_armor_probe")
    state, _frame = _movement_with(engine, 2, "random", "board", 1)
    spaces = encoding.spaces_for(engine.board, len(state.units))
    torch.manual_seed(0)
    policy = Policy(spaces, NetConfig(**SMALL_NET))

    class RideFirst(LearnedAgent):
        """The preference of the failed game: a board, or a debark into the hex of the
        vehicle, over the rest, and end_phase last."""

        def _weapons_handled_last(self, state, ordered, player):
            ordered = LearnedAgent._weapons_handled_last(self, state, ordered, player)

            def in_place(c):
                return c.command.action == "board" or (
                    c.command.action == "debark" and c.command.hex == state.units[c.command.units[0]].hex
                )

            ride = [c for c in ordered if in_place(c)]
            end = [c for c in ordered if c.command.action == "end_phase"]
            rest = [c for c in ordered if c not in ride and c not in end]
            return ride + rest + end

    def rides_in_phase(agent, limit: int) -> tuple[int, bool]:
        current = state
        start = (current.turn, current.phase, current.active)
        count = 0
        for _ in range(limit):
            if (current.turn, current.phase, current.active) != start or current.game_over:
                return count, True
            frame = engine.legal_commands(current)
            legal = frame.by_id(decide(agent, current, frame))
            count += legal.command.action in RIDE_ACTIONS
            current, _ = engine.apply(current, legal.command, frame)
        return count, False

    riders = {u.id for u in state.units if u.player == state.active and u.is_infantry and not u.eliminated}
    count, ended = rides_in_phase(RideFirst.from_policy(engine, policy), 2000)
    assert ended, "the phase ends"
    assert 0 < count <= len(riders), (count, len(riders))

    class GuardOnly(RideFirst):
        """The agent with no limit of its own on a board and a debark: PR-55 holds it."""

        def _rides_handled_last(self, ordered):
            return ordered

    looped, ended = rides_in_phase(GuardOnly.from_policy(engine, policy), 2000)
    assert ended and 0 < looped <= len(riders), (looped, len(riders))
