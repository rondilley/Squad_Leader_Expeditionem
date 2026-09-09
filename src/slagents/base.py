"""The agent interface and the random agent.

In v0.1 the view is the full state, because scenario 1 has no concealment.
The per-player view (AR-09) arrives in v0.3, and the interface does not change.
"""

from __future__ import annotations

from typing import Protocol

from slcore.frame import DecisionFrame
from slcore.game import State
from slcore.rng import RngState, choice_index, seed_state


class Agent(Protocol):
    name: str
    version: str

    def select(self, state: State, frame: DecisionFrame) -> str:
        """Give the ID of one command from the frame."""


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
