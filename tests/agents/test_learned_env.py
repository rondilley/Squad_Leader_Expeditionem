"""The reinforcement learning environment (FR-50, FR-51).

The environment is the only place where the trainer meets the rules, so the tests here
prove three things: it follows the PettingZoo API, its mask allows the legal commands and
nothing else, and its observation holds no unit that the acting player cannot see.
"""

from __future__ import annotations

import pytest

pytest.importorskip("numpy")
pytest.importorskip("gymnasium")
pytest.importorskip("pettingzoo")

import numpy as np

from slagents.learned import encoding
from slagents.learned.env import SquadLeaderEnv, make_env
from slcli.play import build_engine

SCENARIO = "s01_guards_counterattack"


@pytest.fixture(scope="module")
def engine():
    return build_engine(SCENARIO)


def test_the_environment_follows_the_pettingzoo_api(engine):
    """FR-50: the Agent Environment Cycle API.

    The PettingZoo `api_test` helper is not used here. It samples the action space with
    the entry named `action_mask`, and it expects one flat list of actions. The command of
    this game has three parts (FR-51), so a flat list is a quarter of a million entries
    for one scenario and the helper cannot sample a legal one. The API itself is tested
    below, member by member.
    """
    env = SquadLeaderEnv(engine, seed=3, max_commands=400)
    assert env.possible_agents == ["player_0", "player_1"]
    assert env.metadata["name"] == "squad_leader_v0"
    env.reset(seed=3)
    assert env.agents == env.possible_agents
    assert env.agent_selection in env.agents
    for agent in env.agents:
        assert env.observation_space(agent) is env.observation_space(agent)
        assert env.action_space(agent) is env.action_space(agent)
        assert env.observation_space(agent).contains(env.observe(agent))
        assert agent in env.rewards and agent in env.terminations
        assert agent in env.truncations and agent in env.infos
    first = env.last()
    assert len(first) == 5, "last gives the observation, the reward, the two ends, and the info"
    env.step(sorted(env.groups)[0])
    assert env.agent_selection in env.agents
    env.close()


def test_the_agent_iterator_reaches_the_end_of_a_game(engine):
    """The AEC loop of PettingZoo: iterate the agents until each one is done."""
    env = SquadLeaderEnv(engine, seed=19, max_commands=300)
    env.reset(seed=19)
    steps = 0
    for agent in env.agent_iter(max_iter=4000):
        _, _, termination, truncation, _ = env.last()
        if termination or truncation:
            env.step(None)
            continue
        env.step(sorted(env.groups)[0])
        steps += 1
    assert steps > 0
    assert env.agents == [], "each agent is removed after its last step"


def test_the_mask_allows_each_legal_command_and_no_other(engine):
    """FR-50: an illegal command cannot be selected, because the mask does not have it."""
    env = make_env(engine, seed=5)
    for _ in range(40):
        agent = env.agent_selection
        observation = env.observe(agent)
        spaces = env.spaces_record
        action_mask = observation["action_mask"].reshape(spaces.units, spaces.actions)
        allowed = set()
        for unit in np.flatnonzero(observation["unit_mask"]):
            for action in np.flatnonzero(action_mask[unit]):
                for target in np.flatnonzero(env.target_mask(int(unit), int(action))):
                    allowed.add((int(unit), int(action), int(target)))
        assert allowed == set(env.groups), "the mask and the legal list are the same set"
        triple = sorted(env.groups)[0]
        env.step(triple)
        if env.terminations[env.agent_selection]:
            break


def test_a_command_that_the_mask_refuses_raises(engine):
    env = make_env(engine, seed=5)
    with pytest.raises(ValueError) as exc:
        env.step((0, encoding.ACTION_INDEX["group_fire"], 0))
    assert "not legal" in str(exc.value)


def test_the_observation_of_a_player_hides_a_concealed_enemy(engine):
    """SR-09 with rule 25.2: the planes of the other side hold no concealed unit."""
    from slcore.rules import r25_concealment

    env = make_env(engine, seed=7)
    state = env.state_
    enemy = next(u for u in state.player_units(1) if u.is_infantry and u.hex is None)
    hex_ref = engine.board.hex((2, 3)).ref
    state = state.with_unit(enemy.with_(hex=hex_ref))
    env.state_ = state
    env._refresh()
    before = env.observe(env.agent_of(0))
    state, _ = r25_concealment.add(state, 1, hex_ref)
    env.state_ = state
    env._refresh()
    after = env.observe(env.agent_of(0))
    planes = encoding.BOARD_PLANES
    enemy_plane = len(encoding.TERRAIN_KINDS) + 4 + 3
    counter_plane = len(encoding.TERRAIN_KINDS) + 4 + 6 + 1
    assert before["board"][enemy_plane, 2, 3] > 0, "the unit is in the planes with no counter"
    assert after["board"][enemy_plane, 2, 3] == 0, "and it is not there below a counter"
    assert after["board"][counter_plane, 2, 3] == 1.0, "the counter is what the player sees"
    assert after["units"][enemy.id + 1].sum() == 0, "the unit row of a concealed enemy is empty"


def test_the_result_is_the_victory_condition_of_the_game(engine):
    """The result of a game is the victory condition of the scenario and nothing else."""
    env = make_env(engine, seed=11)
    sides = engine.scenario.players()
    assert env._result_reward(env.agent_of(0), sides[0]) == 1.0
    assert env._result_reward(env.agent_of(0), sides[1]) == -1.0
    assert env._result_reward(env.agent_of(0), "draw") == 0.0


def test_a_game_reaches_its_end_and_gives_a_reward(engine):
    """The environment plays a whole game with random legal commands."""
    env = make_env(engine, seed=13)
    rng = np.random.default_rng(0)
    for _ in range(6000):
        agent = env.agent_selection
        if env.terminations[agent] or env.truncations[agent]:
            break
        triples = sorted(env.groups)
        env.step(triples[int(rng.integers(len(triples)))])
    assert env.state_.game_over, "the game reached its end"
    results = [env.results[a] for a in env.possible_agents]
    assert sum(results) == 0.0, "one side wins what the other loses"
    assert any(r != 0.0 for r in results) or env.state_.result == "draw"
    rewards = [env._cumulative_rewards[a] for a in env.possible_agents]
    # The shaped terms are zero-sum, and the step cost is what each command took from the
    # side that gave it. So the two totals add up to minus the step cost of the game.
    # The counts are zero-sum, and each side weighs them by its own doctrine, so the two
    # totals differ. The win and the loss dominate: the winner has the larger total.
    winner = max(range(2), key=lambda p: results[p])
    if results[winner] > 0:
        assert rewards[winner] > rewards[1 - winner], "the winner has the larger total"


def test_the_command_triple_names_the_same_command_in_each_state(engine):
    """FR-51 and TC-38: the three parts are a name, and not a position in a list."""
    env = make_env(engine, seed=17)
    frame = env.frame
    hexes = env.hexes
    for legal in frame.commands[:20]:
        triple = encoding.command_triple(legal.command, hexes)
        assert triple in env.groups
        again = encoding.command_triple(legal.command, hexes)
        assert triple == again
    shuffled = list(reversed(frame.commands))
    groups = encoding.group_commands(type(frame)(frame.frame_id, frame.player, frame.phase, frame.sub_step, frame.turn, tuple(shuffled)), hexes)
    assert set(groups) == set(env.groups), "the parts do not depend on the sequence of the list"


def _play_scripted(env, engine, kinds: tuple[str, str], seed: int) -> tuple[int, int, str]:
    """A whole game of two scripted agents in the environment.

    Gives the decisions the environment asked for, the commands it applied, and the hash of
    the last state.
    """
    from slagents.learned.encoding import command_triple
    from slcli.play import make_agent
    from slcore.hashing import hash_state

    env.reset(seed=seed)
    agents = (make_agent(kinds[0], engine, seed, 0), make_agent(kinds[1], engine, seed, 1))
    decisions = 0
    while True:
        agent = env.agent_selection
        if env.terminations[agent] or env.truncations[agent]:
            break
        state = env.state_
        legal = env.frame.by_id(agents[state.active].select(state, env.frame))
        env.step(command_triple(legal.command, env.hexes))
        decisions += 1
    return decisions, env.commands_applied, hash_state(env.state_)


def test_a_frame_with_one_legal_command_is_applied_and_not_decided(engine):
    """A state with one legal command is not a decision, so the environment applies it.

    The same two scripted agents play the same seed with and without the skip. An agent
    given one legal command gives that command, so the two games are the same game and
    end in the same state, and the environment with the skip asked for fewer decisions
    and never offered a frame with one command.
    """
    asked = make_env(engine, seed=23, skip_forced=False)
    skipped = make_env(engine, seed=23, skip_forced=True)
    decisions_asked, applied_asked, last_asked = _play_scripted(asked, engine, ("v5", "v1"), 23)
    assert skipped.forced_applied == 0
    decisions_skipped, applied_skipped, last_skipped = _play_scripted(skipped, engine, ("v5", "v1"), 23)
    assert last_skipped == last_asked, "the same game with and without the skip"
    assert applied_skipped == applied_asked, "the same commands went onto the state"
    assert decisions_skipped + skipped.forced_applied == decisions_asked
    assert skipped.forced_applied > 50, "a game of scenario 1 has many forced frames"
    assert decisions_skipped < decisions_asked


def test_the_environment_with_the_skip_never_offers_one_choice(engine):
    """Each frame the environment offers holds two or more commands, from the reset on."""
    env = make_env(engine, seed=29)
    rng = np.random.default_rng(29)
    seen = 0
    while seen < 300:
        agent = env.agent_selection
        if env.terminations[agent] or env.truncations[agent]:
            env.reset(seed=env.seed_value + 1)
            continue
        assert len(env.groups) >= 2, f"a frame with {len(env.groups)} command was offered"
        triples = sorted(env.groups)
        env.step(triples[int(rng.integers(len(triples)))])
        seen += 1
    assert env.forced_applied > 0


def test_the_observation_shows_the_fire_group_the_legal_units_and_the_objective(engine):
    """The rows say who is in the fire group and who can act, and the planes say the objective and its holder.

    The imitation of 2026-09-16 fired a group at the teacher's moment in no state, because
    a group of one and a group of five looked the same to the policy.
    """
    from slcore.game import PHASE_PREP_FIRE
    from slcore.rules.victory import controlled_by
    from slagents.learned.encoding import command_triple
    from slcli.play import make_agent

    env = make_env(engine, seed=43)
    agents = (make_agent("v5", engine, 43, 0), make_agent("v6", engine, 43, 1))
    # Play to a Prep Fire Phase in which a group has a member and the next command is open.
    for _ in range(4000):
        state = env.state_
        assert not state.game_over
        if state.phase == PHASE_PREP_FIRE and state.fire_group is not None and state.fire_group.members:
            break
        legal = env.frame.by_id(agents[state.active].select(state, env.frame))
        env.step(command_triple(legal.command, env.hexes))
    else:
        raise AssertionError("no open fire group in 4000 commands")
    state = env.state_
    player = state.active
    observation = env.observe(env.agent_of(player))
    group = state.fire_group
    members = {m[0] for m in group.members}
    for unit in state.player_units(player):
        row = observation["units"][unit.id + 1]
        if unit.eliminated:
            continue
        assert row[26] == (1.0 if unit.id in members else 0.0), f"unit {unit.id} in the group"
        assert row[28] == float(observation["unit_mask"][unit.id + 1]), f"unit {unit.id} has a legal command"
    assert any(observation["units"][m + 1][26] == 1.0 for m in members)
    target_plane = len(encoding.TERRAIN_KINDS) + 14
    assert observation["board"][target_plane, group.target[0], group.target[1]] == 1.0
    assert observation["board"][target_plane].sum() == 1.0, "one target hex"
    # The objective planes: the buildings of the victory condition, and who holds each one.
    objective_plane = target_plane + 1
    assert env.objectives.buildings, "scenario 1 names buildings"
    assert observation["board"][objective_plane].sum() == sum(len(h) for _, h in env.objectives.buildings)
    for building, hexes in env.objectives.buildings:
        for col, row_index in hexes:
            assert observation["board"][objective_plane + 1, col, row_index] == (1.0 if controlled_by(state, engine.board, building, player) else 0.0)
            assert observation["board"][objective_plane + 2, col, row_index] == (1.0 if controlled_by(state, engine.board, building, 1 - player) else 0.0)
    # The other side, which does not act, reads no legal unit and sees the same group.
    other = env.observe(env.agent_of(1 - player))
    assert other["units"][:, 28].sum() == 0.0
    assert other["board"][target_plane].sum() == 1.0
