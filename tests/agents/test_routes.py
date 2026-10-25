"""The route action and the no-return filter of the Movement Phase (2026-10-20).

The design is `docs/reports/2026-10-20_attack_movement_design.md`. A net selects a
destination for a unit or a stack, and the environment and the agent play its single steps
through the core. A move of a unit into a hex that it held in the phase is a return, and the
masks leave it out.
"""

from __future__ import annotations

import pytest

pytest.importorskip("numpy")
pytest.importorskip("torch")
pytest.importorskip("gymnasium")
pytest.importorskip("pettingzoo")

import numpy as np

from slagents.base import decide
from slagents.learned import encoding, routes
from slagents.learned.env import make_env
from slcli.play import build_engine, make_agent, play_game, replay_record

SCENARIO = "lib02_pump_house"
SEED = 900101


@pytest.fixture(scope="module")
def engine():
    return build_engine(SCENARIO)


def _to_movement(env, engine, turn: int = 1, player: int = 0, stacks: bool = False):
    """Play v7 on the two sides to the first Movement Phase of `player` in `turn` or later."""
    agents = {p: make_agent("v7", engine, SEED, p) for p in (0, 1)}
    for _ in range(20000):
        state, frame = env.state_, env.frame
        assert not state.game_over, "the game ended before the Movement Phase"
        if frame.phase == "movement" and frame.player == player and state.turn >= turn:
            if not stacks or any(c.command.action == "stack_move" for c in frame.commands):
                return
        legal = frame.by_id(decide(agents[frame.player], state, frame))
        env.step(encoding.command_index(legal, env.groups))
    raise AssertionError("no Movement Phase in 20000 commands")


def test_a_route_replaces_the_single_steps_of_its_unit(engine):
    env = make_env(engine, seed=SEED)
    assert env.use_routes, "a new environment has the routes of the new action list"
    _to_movement(env, engine)
    assert env.routes, "a Movement Phase with movers has routes"
    covered = {(route.step, route.units) for route, _ in env.routes.values()}
    for key, legal in env.choices.items():
        if key in env.routes:
            continue
        assert (legal.command.action, tuple(legal.command.units)) not in covered, "a single step of a unit with a route is not a choice"
    for key, (route, first) in env.routes.items():
        assert first.id in {c.id for c in env.frame.commands}, "the first step of each route is a legal command"
        assert first.command.hex == route.path[0]
        assert key[2] == env.hexes[route.destination]
    spaces = env.spaces_record
    observation = env.observe(env.agent_selection)
    action_mask = observation["action_mask"].reshape(spaces.units, spaces.actions)
    allowed = set()
    for unit in np.flatnonzero(observation["unit_mask"]):
        for action in np.flatnonzero(action_mask[unit]):
            for target in np.flatnonzero(env.target_mask(int(unit), int(action))):
                for option in np.flatnonzero(env.option_mask(int(unit), int(action), int(target))):
                    allowed.add((int(unit), int(action), int(target), int(option)))
    assert allowed == set(env.choices), "the masks give the routes and the other choices"


def test_a_route_is_one_decision_and_ends_at_its_destination(engine):
    env = make_env(engine, seed=SEED)
    _to_movement(env, engine)
    key, (route, _) = max(((k, v) for k, v in env.routes.items() if v[0].action == routes.ROUTE), key=lambda kv: (len(kv[1][0].path), kv[0]))
    assert len(route.path) > 1, "the test needs a route of two steps or more"
    before = env.commands_applied
    env.step(key)
    unit = env.state_.unit(route.lead)
    assert unit.hex == route.destination
    assert unit.track == route.path, "the core played each step of the path"
    assert env.commands_applied - before == len(route.path)
    assert (env.frame.phase, env.frame.player) == ("movement", 0), "the phase goes on after the route"
    for other, _ in env.routes.values():
        if other.lead == route.lead:
            assert other.destination not in route.path and other.destination != route.start, "no route goes back to a held hex"


def test_a_stack_route_moves_the_leader_and_its_squads(engine):
    env = make_env(engine, seed=SEED)
    _to_movement(env, engine, turn=2, stacks=True)
    stack = [(k, v) for k, v in env.routes.items() if v[0].action == routes.STACK_ROUTE]
    assert stack, "a leader beside a squad has stack routes"
    key, (route, _) = max(stack, key=lambda kv: (len(kv[1][0].path), kv[0]))
    env.step(key)
    for uid in route.units:
        assert env.state_.unit(uid).hex == route.destination


def test_the_stack_option_is_the_same_stack_in_two_positions(engine):
    """The option of a `stack_move` is its place in the command IDs, which are hashes. The
    option of a `stack_route` is the bit mask of its squads by unit ID, so it does not change
    when another unit moves."""
    env = make_env(engine, seed=SEED)
    _to_movement(env, engine, turn=2, stacks=True)
    stacks = {(r.units, k[3]) for k, (r, _) in env.routes.items() if r.action == routes.STACK_ROUTE}
    solo = [(k, v) for k, v in env.routes.items() if v[0].action == routes.ROUTE and not any(v[0].lead in units for units, _ in stacks)]
    assert stacks and solo, "the test needs a stack and another unit that moves"
    env.step(solo[0][0])
    after = {(r.units, k[3]) for k, (r, _) in env.routes.items() if r.action == routes.STACK_ROUTE}
    assert stacks & after, "a stack keeps its option after another unit moved"
    for units, option in after:
        assert option == routes.stack_option(env.state_, next(u for u in units if env.state_.unit(u).kind == "leader"), units)


def test_a_route_ends_when_its_unit_is_not_where_the_route_left_it(engine):
    env = make_env(engine, seed=SEED)
    _to_movement(env, engine)
    route, _ = next(iter(env.routes.values()))
    moved = routes.Route(route.action, route.units, route.lead, route.start, ((99, 99),) + route.path)
    assert routes.next_step(moved, 1, env.state_, env.frame) is None, "the unit is not at the first hex of the path"
    assert routes.next_step(route, len(route.path), env.state_, env.frame) is None, "a route ends at its destination"


def test_a_move_back_into_a_held_hex_is_not_a_choice(engine):
    """The L02 clone moved one squad eight times between two hexes in one phase, and no
    position repeated, because each step used a movement factor (2026-10-20)."""
    env = make_env(engine, seed=SEED, use_routes=False)
    assert not env.use_routes
    _to_movement(env, engine)
    key = next(k for k, c in sorted(env.groups.items()) if c.command.action == "move")
    command = env.groups[key].command
    start = env.state_.unit(command.units[0]).hex
    env.step(key)
    back = {k for k, c in env.groups.items() if c.command.action == "move" and c.command.units == command.units and c.command.hex == start}
    assert back, "the core offers the move back"
    assert not back & set(env.choices), "the masks leave it out"
    assert set(env.choices) <= set(env.groups)


def test_without_returns_keeps_each_choice_when_only_returns_are_legal(engine):
    env = make_env(engine, seed=SEED, use_routes=False)
    _to_movement(env, engine)
    memory = routes.PhaseMemory()
    memory.update(env.state_, 0)
    moves = {k: c for k, c in env.groups.items() if c.command.action == "move"}
    for c in moves.values():
        memory.held.setdefault(c.command.units[0], set()).add(c.command.hex)
    assert routes.without_returns(moves, memory) == moves


def test_a_net_from_before_the_routes_plays_with_its_own_actions(engine):
    import torch

    from slagents.learned.agent import LearnedAgent
    from slagents.learned.nets import NetConfig, Policy

    env = make_env(engine, seed=SEED, use_routes=False)
    assert env.spaces_record.actions == encoding.ACTION_INDEX[routes.ROUTE]
    torch.manual_seed(1)
    policy = Policy(env.spaces_record, NetConfig(channels=4, hidden=32, board_width=32, unit_width=16))
    agent = LearnedAgent.from_policy(engine, policy)
    assert not agent.uses_routes
    _to_movement(env, engine)
    chosen = env.frame.by_id(agent.select(env.state_, env.frame))
    assert chosen is not None and agent._plan is None


def test_a_net_with_routes_plays_a_game_to_the_end_and_the_replay_agrees():
    import torch

    from slagents.learned.agent import LearnedAgent
    from slagents.learned.nets import NetConfig, Policy

    engine = build_engine("s01_guards_counterattack")
    spaces = encoding.spaces_for(engine.board, len(engine.new_game(3).units))
    assert routes.uses_routes(spaces)
    torch.manual_seed(2)
    policy = Policy(spaces, NetConfig(channels=4, hidden=32, board_width=32, unit_width=16))
    learner = LearnedAgent.from_policy(engine, policy)
    record = play_game(engine, 3, (learner, make_agent("v1", engine, 3, 1)))
    assert record.result
    assert replay_record(engine, record), "the command log holds the single steps of the core"
    moves = [c for c in record.commands if c["player"] == 0 and c["payload"]["action"] == "move"]
    assert moves, "the net moved"


def test_a_run_of_moves_of_the_teacher_is_one_route_row(engine):
    """The teacher moves one hex at a time. A run of its moves of one unit or stack in a
    phase is one row, whose label is the route to the last hex of the run."""
    from slagents.learned.imitate import play_demonstration

    env = make_env(engine, seed=SEED)
    data, _ = play_demonstration(env, lambda kind, seed, player: make_agent(kind, engine, seed, player), "v7", "v7", SEED)
    actions = [encoding.ACTIONS[a] for a in data.field("action")]
    assert actions.count("route") > 0 and actions.count("stack_route") > 0
    assert actions.count("move") + actions.count("stack_move") == 0, "a single step of a unit with a route is not a label"
    assert env.state_.game_over, "the game ran to its end"
