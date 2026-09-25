"""The agent interface, the one call that gives an agent its decision, and the random agent.

An agent never reads the authoritative state (S3 of the 2026-09-23 review). Each caller
asks for a decision through `decide`, which gives the agent the state as the acting player
may know it (`slcore.player_state.for_player`): no enemy unit that the view hides, and no
true generator state. The frame is the true legal list of the acting seat, because the
legal list does not tell a dummy from a real stack (PR-31).
"""

from __future__ import annotations

from typing import Protocol

from slcore.frame import DecisionFrame
from slcore.game import State
from slcore.player_state import for_player
from slcore.rng import RngState, choice_index, seed_state


class Agent(Protocol):
    name: str
    version: str

    def select(self, state: State, frame: DecisionFrame) -> str:
        """Give the ID of one command from the frame."""


def decide(agent: Agent, state: State, frame: DecisionFrame) -> str:
    """The command ID that this agent selects, from the state its player may know."""
    return agent.select(for_player(state, frame.player), frame)


class RandomAgent:
    """Selects a uniform random legal command. Its generator is its own, seeded from the game seed and the player."""

    name = "random"
    version = "0.1"

    def __init__(self, seed: int, player: int) -> None:
        self.rng: RngState = seed_state((seed * 2 + player) ^ 0x5EED)

    def select(self, state: State, frame: DecisionFrame) -> str:
        if not frame.commands:
            raise ValueError("no legal command")
        self.rng, i = choice_index(self.rng, len(frame.commands))
        return frame.commands[i].id
