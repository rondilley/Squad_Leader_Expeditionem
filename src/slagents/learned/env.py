"""The reinforcement learning environment (FR-50).

The environment follows the PettingZoo Agent Environment Cycle API. Two agents take turns,
and the environment says which one acts. Each observation carries the legal-command mask,
so an agent cannot select a command that the rules refuse.

The mask has four parts: which unit, which action, which hex, and which option when two
commands share the first three. The unit mask and the action mask are in the observation.
The target mask comes from `target_mask`, and the option mask from `option_mask`, because
a mask over each unit, each action, and each hex is a hundred times larger than the state.

The reward is the shaped reward of `slagents.learned.reward`: the result of the game, from
the victory conditions of the scenario (FR-14), plus the terms that lead to it (find, fire,
hurt, kill, cover, sneak, hide, survive, the objective) and their costs. The first rung of
the ladder ran on the result alone and learned a loop, because a game that never ends was
worth more than a loss (`docs/reports/2026-09-12_training_run_1m.md`). A truncated game is
a defeat now. The result of the game on its own is in `results`, for the league and the
evaluation, because a win is a win whatever the shaped total says. A repeated state ends
the game as a defeat of the side that repeated it, because a repeated state is a cycle.

A state with one legal command is not a decision. The environment applies that command
itself and asks the agent at the next state that has two or more, because a decision
with one choice is a quarter of a game of scenario 1 (173 of 756 commands of a game of
v6 against v1, most of them `end_phase` and the `group_fire` of a group with one target),
and each one was a step of the rollout, a row of the demonstrations, and a step cost, for
nothing the policy could learn. The scripted agents give the same game with and without
this, because an agent given one legal command gives that command.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
from gymnasium import spaces as gym_spaces
from pettingzoo import AECEnv

from slagents.learned import encoding
from slagents.learned.encoding import position_key
from slagents.learned.reward import RewardWeights, objective_progress, result_rewards, step_rewards, weights_for_scenario
from slcore.engine import Engine
from slcore.frame import DecisionFrame
from slcore.game import State

AGENT_NAMES = ("player_0", "player_1")
MAX_COMMANDS = 20000
# The result of a game on its own, for the league and the evaluation (TC-18, TC-19).
WIN = 1.0
LOSS = -1.0
DRAW = 0.0


class NoLegalCommand(RuntimeError):
    """The core gave a state with no legal command, which is a defect in the core."""


class SquadLeaderEnv(AECEnv):
    """One scenario as a two-agent environment.

    The environment holds an Engine and a State. It does not hold a rule: each legal
    command and each result comes from `legal_commands` and `apply` (AR-01).
    """

    metadata = {"render_modes": [], "name": "squad_leader_v0", "is_parallelizable": False}

    def __init__(
        self,
        engine: Engine,
        seed: int = 1,
        max_commands: int = MAX_COMMANDS,
        weights: RewardWeights | tuple[RewardWeights, RewardWeights] | None = None,
        skip_forced: bool = True,
    ) -> None:
        super().__init__()
        self.engine = engine
        self.seed_value = seed
        self.max_commands = max_commands
        # A frame with one legal command is applied by the environment, not decided.
        self.skip_forced = skip_forced
        self.forced_applied = 0
        # Each side weighs the same events by the doctrine of the army it fields (RV-9,
        # table B). One RewardWeights serves both sides when a caller gives one.
        if weights is None:
            self.weights: tuple[RewardWeights, RewardWeights] = weights_for_scenario(engine)
        elif isinstance(weights, tuple):
            self.weights = weights
        else:
            self.weights = (weights, weights)
        self.results: dict[str, float] = {}
        self.progress: tuple[int, int] = (0, 0)
        self.spaces_record = encoding.spaces_for(engine.board, len(engine.new_game(seed).units))
        self.hexes = encoding.hex_slots(engine.board)
        self.objectives = encoding.objectives_for(engine)
        self.possible_agents = list(AGENT_NAMES)
        self.agents: list[str] = []
        self.state_: State | None = None
        self.frame: DecisionFrame | None = None
        self.groups: dict[tuple[int, int, int, int], Any] = {}
        self.commands_applied = 0
        self._observation_space = gym_spaces.Dict(
            {
                "board": gym_spaces.Box(low=0.0, high=8.0, shape=self.spaces_record.board_shape, dtype=np.float32),
                "units": gym_spaces.Box(low=-1.0, high=8.0, shape=self.spaces_record.unit_shape, dtype=np.float32),
                "scalars": gym_spaces.Box(low=-1.0, high=8.0, shape=(encoding.SCALARS,), dtype=np.float32),
                "unit_mask": gym_spaces.MultiBinary(self.spaces_record.units),
                "action_mask": gym_spaces.MultiBinary(self.spaces_record.units * self.spaces_record.actions),
            }
        )
        self._action_space = gym_spaces.MultiDiscrete(
            [
                self.spaces_record.units,
                self.spaces_record.actions,
                self.spaces_record.targets,
                self.spaces_record.options,
            ]
        )

    # ------------------------------------------------------------- the API

    def observation_space(self, agent: str) -> gym_spaces.Space:
        return self._observation_space

    def action_space(self, agent: str) -> gym_spaces.Space:
        return self._action_space

    def reset(self, seed: int | None = None, options: Mapping[str, Any] | None = None) -> None:
        if seed is not None:
            self.seed_value = int(seed)
        self.agents = list(self.possible_agents)
        self.rewards = {a: 0.0 for a in self.agents}
        self._cumulative_rewards = {a: 0.0 for a in self.agents}
        self.terminations = {a: False for a in self.agents}
        self.truncations = {a: False for a in self.agents}
        self.infos: dict[str, dict[str, Any]] = {a: {} for a in self.agents}
        self.results = {a: 0.0 for a in self.agents}
        self.state_ = self.engine.new_game(self.seed_value)
        self.commands_applied = 0
        self.forced_applied = 0
        self.seen = {position_key(self.state_)}
        self.repeated = False
        self.progress = objective_progress(self.engine, self.state_)
        self._refresh()
        self._apply_forced()

    def observe(self, agent: str) -> dict[str, np.ndarray]:
        player = self.player_of(agent)
        state = self._state()
        frame = self.frame
        if frame is None:
            raise RuntimeError("the environment has no frame; call reset first")
        unit_mask, action_mask = encoding.masks_from(self.groups, self.spaces_record)
        if player != frame.player:
            unit_mask = np.zeros_like(unit_mask)
            action_mask = np.zeros_like(action_mask)
        legal_units = [int(i) for i in np.flatnonzero(unit_mask)]
        return {
            "board": encoding.board_tensor(
                self.engine.board, state, self.engine.types, player, self.spaces_record, self.objectives
            ),
            "units": encoding.unit_tensor(
                state, self.engine.types, player, self.spaces_record, self.engine.board, legal_units
            ),
            "scalars": encoding.scalar_vector(state, frame, player),
            "unit_mask": unit_mask,
            "action_mask": action_mask.reshape(-1),
        }

    def step(self, action: Any) -> None:
        """One composed command: the unit slot, the action, the target slot, and the option.

        A caller that passes three numbers gets option 0, the lowest command id of that
        triple. Two weapons at one hex need the fourth number.
        """
        agent = self.agent_selection
        if self.terminations[agent] or self.truncations[agent]:
            self._was_dead_step(action)
            return
        if len(action) >= 4:
            key = (int(action[0]), int(action[1]), int(action[2]), int(action[3]))
        else:
            key = (int(action[0]), int(action[1]), int(action[2]), 0)
        legal = self.groups.get(key)
        if legal is None:
            raise ValueError(f"the command {key} is not legal in this state; read the masks")
        self._apply(legal, self.player_of(agent))
        self._apply_forced()

    def target_mask(self, unit: int, action: int) -> np.ndarray:
        """The third head: which hexes this unit and this action allow (FR-50)."""
        return encoding.target_mask_for(self.groups, self.spaces_record, unit, action)

    def option_mask(self, unit: int, action: int, target: int) -> np.ndarray:
        """The fourth head: which command of this unit, action, and hex is legal."""
        return encoding.option_mask_for(self.groups, self.spaces_record, unit, action, target)

    def close(self) -> None:
        return None

    # ---------------------------------------------------------------- inside

    def player_of(self, agent: str) -> int:
        return self.possible_agents.index(agent)

    def agent_of(self, player: int) -> str:
        return self.possible_agents[player]

    def _state(self) -> State:
        if self.state_ is None:
            raise RuntimeError("the environment has no state; call reset first")
        return self.state_

    def _apply(self, legal: Any, acted: int) -> None:
        """One legal command of the side `acted` onto the state, with its rewards and ends."""
        before = self._state()
        state, events = self.engine.apply(before, legal.command, self.frame)
        self.state_ = state
        self.commands_applied += 1
        digest = position_key(state)
        repeated = digest in self.seen
        self.seen.add(digest)
        self._rewards_and_ends(before, events, acted, repeated)
        self._refresh()

    def _apply_forced(self) -> None:
        """Apply each frame that holds one legal command, until a frame holds a choice.

        The command goes to the side the frame names, with its step cost, and the rewards
        of what it gives accrue to the decision before it, which is the decision that led
        here. A loop and not a recursion, because a run of forced frames has no bound.
        """
        if not self.skip_forced:
            return
        while len(self.groups) == 1 and not self._ended():
            self.forced_applied += 1
            self._apply(next(iter(self.groups.values())), self.frame.player)

    def _ended(self) -> bool:
        return any(self.terminations.values()) or any(self.truncations.values())

    def _refresh(self) -> None:
        state = self._state()
        self.frame = self.engine.legal_commands(state)
        self.groups = encoding.group_commands(self.frame, self.hexes)
        self.agent_selection = self.agent_of(self.frame.player)
        if state.game_over:
            return
        if not self.frame.commands:
            raise NoLegalCommand(f"no legal command in {state.phase}/{self.frame.sub_step}")

    def _rewards_and_ends(self, before: State, events: list, acted: int, repeated: bool = False) -> None:
        state = self._state()
        shaped, self.progress = step_rewards(self.engine, before, state, events, acted, self.weights, self.progress)
        self.rewards = {self.agent_of(0): shaped[0], self.agent_of(1): shaped[1]}
        over = state.game_over
        long = self.commands_applied >= self.max_commands
        if repeated and not over:
            # A repeated state is a cycle: the command undid a command before it and the
            # game cannot go on from here. The second shaped run learned a pickup and a
            # drop again, because a discount below one hid the cost of the command limit
            # twenty thousand commands away. So the cycle is a defeat for the side that
            # made it, on the spot, with no discount between the loop and its cost.
            self.repeated = True
            self.rewards[self.agent_of(acted)] += self.weights[acted].loss
            for agent in self.agents:
                self.results[agent] = DRAW
                self.truncations[agent] = True
            self._accumulate_rewards()
            return
        if not over and not long:
            self._accumulate_rewards()
            return
        terminal = result_rewards(self.engine, state.result, not over, self.weights)
        for agent in self.agents:
            self.rewards[agent] += terminal[self.player_of(agent)]
            self.results[agent] = self._result_reward(agent, state.result) if over else DRAW
            if over:
                self.terminations[agent] = True
            else:
                self.truncations[agent] = True
        self._accumulate_rewards()

    def _result_reward(self, agent: str, result: str) -> float:
        sides = self.engine.scenario.players()
        side = sides[self.player_of(agent)]
        if result == side:
            return WIN
        if result in sides:
            return LOSS
        return DRAW


def make_env(
    engine: Engine,
    seed: int = 1,
    max_commands: int = MAX_COMMANDS,
    weights: RewardWeights | tuple[RewardWeights, RewardWeights] | None = None,
    skip_forced: bool = True,
) -> SquadLeaderEnv:
    env = SquadLeaderEnv(engine, seed=seed, max_commands=max_commands, weights=weights, skip_forced=skip_forced)
    env.reset(seed=seed)
    return env
