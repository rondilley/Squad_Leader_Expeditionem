"""The reinforcement learning environment (FR-50).

The environment follows the PettingZoo Agent Environment Cycle API. Two agents take turns,
and the environment says which one acts. Each observation carries the legal-command mask,
so an agent cannot select a command that the rules refuse.

The mask has three parts, because the command has three parts (FR-51): which unit, which
action, and which hex. The unit mask and the action mask are in the observation. The
target mask comes from `target_mask`, because a mask over each unit, each action, and each
hex is a hundred times larger than the state, and the policy asks for one row of it.

The reward is the result of the game and nothing else: plus one for a win, minus one for a
loss, zero for a draw. The core says who won, and it says so from the victory conditions of
the scenario (FR-14). A reward for a broken enemy squad would teach the agent to break
squads, and the game is about buildings.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
from gymnasium import spaces as gym_spaces
from pettingzoo import AECEnv

from slagents.learned import encoding
from slcore.engine import Engine
from slcore.frame import DecisionFrame
from slcore.game import State

AGENT_NAMES = ("player_0", "player_1")
MAX_COMMANDS = 20000
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

    def __init__(self, engine: Engine, seed: int = 1, max_commands: int = MAX_COMMANDS) -> None:
        super().__init__()
        self.engine = engine
        self.seed_value = seed
        self.max_commands = max_commands
        self.spaces_record = encoding.spaces_for(engine.board, len(engine.new_game(seed).units))
        self.hexes = encoding.hex_slots(engine.board)
        self.possible_agents = list(AGENT_NAMES)
        self.agents: list[str] = []
        self.state_: State | None = None
        self.frame: DecisionFrame | None = None
        self.groups: dict[tuple[int, int, int], Any] = {}
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
            [self.spaces_record.units, self.spaces_record.actions, self.spaces_record.targets]
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
        self.state_ = self.engine.new_game(self.seed_value)
        self.commands_applied = 0
        self._refresh()

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
        return {
            "board": encoding.board_tensor(self.engine.board, state, self.engine.types, player, self.spaces_record),
            "units": encoding.unit_tensor(state, self.engine.types, player, self.spaces_record, self.engine.board),
            "scalars": encoding.scalar_vector(state, frame, player),
            "unit_mask": unit_mask,
            "action_mask": action_mask.reshape(-1),
        }

    def step(self, action: Any) -> None:
        """One composed command: the unit slot, the action, and the target slot."""
        agent = self.agent_selection
        if self.terminations[agent] or self.truncations[agent]:
            self._was_dead_step(action)
            return
        triple = (int(action[0]), int(action[1]), int(action[2]))
        legal = self.groups.get(triple)
        if legal is None:
            raise ValueError(f"the command {triple} is not legal in this state; read the masks")
        state, _ = self.engine.apply(self._state(), legal.command, self.frame)
        self.state_ = state
        self.commands_applied += 1
        self._rewards_and_ends()
        self._refresh()

    def target_mask(self, unit: int, action: int) -> np.ndarray:
        """The third head: which hexes this unit and this action allow (FR-50)."""
        return encoding.target_mask_for(self.groups, self.spaces_record, unit, action)

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

    def _refresh(self) -> None:
        state = self._state()
        self.frame = self.engine.legal_commands(state)
        self.groups = encoding.group_commands(self.frame, self.hexes)
        self.agent_selection = self.agent_of(self.frame.player)
        if state.game_over:
            return
        if not self.frame.commands:
            raise NoLegalCommand(f"no legal command in {state.phase}/{self.frame.sub_step}")

    def _rewards_and_ends(self) -> None:
        state = self._state()
        self.rewards = {a: 0.0 for a in self.agents}
        over = state.game_over
        long = self.commands_applied >= self.max_commands
        if not over and not long:
            self._accumulate_rewards()
            return
        if over:
            for agent in self.agents:
                self.rewards[agent] = self._result_reward(agent, state.result)
                self.terminations[agent] = True
        else:
            for agent in self.agents:
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


def make_env(engine: Engine, seed: int = 1, max_commands: int = MAX_COMMANDS) -> SquadLeaderEnv:
    env = SquadLeaderEnv(engine, seed=seed, max_commands=max_commands)
    env.reset(seed=seed)
    return env
