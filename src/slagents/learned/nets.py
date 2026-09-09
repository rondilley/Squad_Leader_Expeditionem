"""The policy and value network of the learned agent (FR-51).

The command has three parts, so the policy has three heads and they are read in sequence:
the unit head selects a unit slot, the action head reads that unit, and the target head
reads the unit and the action. The value head reads the state alone.

The three heads are the reason the network is not a single softmax over a flat list. A
flat list over each unit, each action, and each hex is a quarter of a million entries for
one scenario, and most of them are illegal in each state. Three small heads with a mask on
each one give the same set of commands and a hundred times fewer parameters.

The encoder is small on purpose. The board is at most 33 by 11 hexes, so two convolutions
and a linear layer read it. A larger encoder waits for a measurement that asks for one.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn

from slagents.learned.encoding import BOARD_PLANES, SCALARS, UNIT_FEATURES, Spaces

NEGATIVE = -1e9


@dataclass(frozen=True)
class NetConfig:
    """The shape of the network. A run artifact records it, so a snapshot loads again."""

    channels: int = 32
    board_width: int = 256
    unit_width: int = 64
    hidden: int = 256

    def to_dict(self) -> dict[str, int]:
        return {
            "channels": self.channels,
            "board_width": self.board_width,
            "unit_width": self.unit_width,
            "hidden": self.hidden,
        }


def masked_logits(logits: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """A mask of zero makes a command impossible, and not merely unlikely."""
    return logits.masked_fill(mask <= 0, NEGATIVE)


class Policy(nn.Module):
    """The composed policy of FR-51 and the value of the state."""

    def __init__(self, spaces: Spaces, config: NetConfig | None = None) -> None:
        super().__init__()
        self.spaces = spaces
        self.config = config or NetConfig()
        c = self.config
        self.board = nn.Sequential(
            nn.Conv2d(BOARD_PLANES, c.channels, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv2d(c.channels, c.channels, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Flatten(),
            nn.Linear(c.channels * spaces.cols * (spaces.rows + 1), c.board_width),
            nn.ReLU(),
        )
        self.unit = nn.Sequential(
            nn.Linear(UNIT_FEATURES, c.unit_width),
            nn.ReLU(),
            nn.Linear(c.unit_width, c.unit_width),
            nn.ReLU(),
        )
        self.trunk = nn.Sequential(
            nn.Linear(c.board_width + SCALARS + c.unit_width, c.hidden),
            nn.ReLU(),
        )
        self.unit_head = nn.Linear(c.hidden + c.unit_width, 1)
        self.action_head = nn.Sequential(
            nn.Linear(c.hidden + c.unit_width, c.hidden),
            nn.ReLU(),
            nn.Linear(c.hidden, spaces.actions),
        )
        self.action_embed = nn.Embedding(spaces.actions, c.unit_width)
        self.target_head = nn.Sequential(
            nn.Linear(c.hidden + c.unit_width * 2, c.hidden),
            nn.ReLU(),
            nn.Linear(c.hidden, spaces.targets),
        )
        self.value_head = nn.Sequential(
            nn.Linear(c.hidden, c.hidden),
            nn.ReLU(),
            nn.Linear(c.hidden, 1),
        )

    # ----------------------------------------------------------------- parts

    def encode(self, board: torch.Tensor, units: torch.Tensor, scalars: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """The state embedding and the embedding of each unit slot."""
        board_embedding = self.board(board)
        unit_embeddings = self.unit(units)
        pooled = unit_embeddings.mean(dim=1)
        trunk = self.trunk(torch.cat([board_embedding, scalars, pooled], dim=-1))
        return trunk, unit_embeddings

    def unit_logits(self, trunk: torch.Tensor, unit_embeddings: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        repeated = trunk.unsqueeze(1).expand(-1, unit_embeddings.shape[1], -1)
        joined = torch.cat([repeated, unit_embeddings], dim=-1)
        return masked_logits(self.unit_head(joined).squeeze(-1), mask)

    def action_logits(
        self, trunk: torch.Tensor, unit_embeddings: torch.Tensor, unit: torch.Tensor, mask: torch.Tensor
    ) -> torch.Tensor:
        chosen = self._gather_units(unit_embeddings, unit)
        return masked_logits(self.action_head(torch.cat([trunk, chosen], dim=-1)), mask)

    def target_logits(
        self,
        trunk: torch.Tensor,
        unit_embeddings: torch.Tensor,
        unit: torch.Tensor,
        action: torch.Tensor,
        mask: torch.Tensor,
    ) -> torch.Tensor:
        chosen = self._gather_units(unit_embeddings, unit)
        acted = self.action_embed(action)
        return masked_logits(self.target_head(torch.cat([trunk, chosen, acted], dim=-1)), mask)

    def value(self, trunk: torch.Tensor) -> torch.Tensor:
        return self.value_head(trunk).squeeze(-1)

    @staticmethod
    def _gather_units(unit_embeddings: torch.Tensor, unit: torch.Tensor) -> torch.Tensor:
        index = unit.view(-1, 1, 1).expand(-1, 1, unit_embeddings.shape[-1])
        return unit_embeddings.gather(1, index).squeeze(1)

    # ------------------------------------------------------------- the whole

    def evaluate(
        self,
        board: torch.Tensor,
        units: torch.Tensor,
        scalars: torch.Tensor,
        unit_mask: torch.Tensor,
        action_mask: torch.Tensor,
        target_mask: torch.Tensor,
        unit: torch.Tensor,
        action: torch.Tensor,
        target: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """The log probability of the chosen command, the entropy, and the value."""
        trunk, unit_embeddings = self.encode(board, units, scalars)
        u_logits = self.unit_logits(trunk, unit_embeddings, unit_mask)
        u_dist = torch.distributions.Categorical(logits=u_logits)
        a_mask = action_mask.gather(1, unit.view(-1, 1, 1).expand(-1, 1, action_mask.shape[-1])).squeeze(1)
        a_logits = self.action_logits(trunk, unit_embeddings, unit, a_mask)
        a_dist = torch.distributions.Categorical(logits=a_logits)
        t_logits = self.target_logits(trunk, unit_embeddings, unit, action, target_mask)
        t_dist = torch.distributions.Categorical(logits=t_logits)
        log_prob = u_dist.log_prob(unit) + a_dist.log_prob(action) + t_dist.log_prob(target)
        entropy = u_dist.entropy() + a_dist.entropy() + t_dist.entropy()
        return log_prob, entropy, self.value(trunk)
