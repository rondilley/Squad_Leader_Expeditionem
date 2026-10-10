"""The trained policy as a normal computer opponent (FR-51, FR-52).

A snapshot from `sl-cli train` is a policy that only the training environment could drive.
This wrapper gives it the Agent interface, so it plays in a tournament, a gate, and a real
game the same way a scripted agent does.

The wrapper scores the legal commands that the core offers and returns the ID of the best
one. It does not sample a triple and hope the triple is legal: it reads `frame.commands`,
maps each legal command to its three parts with the same `command_triple` the trainer uses,
and scores each triple with the policy's three heads. The command with the highest score is
the choice. So the returned ID is always a real legal command, and the target mask does not
have to be rebuilt outside the environment.

The score of a command is the sum of the three per-head log probabilities, which is how
`ppo.choose` composes the log probability of a whole command. The default is the argmax,
because a tournament and a replay must give the same command for the same state. A seed
turns on sampling for a run that wants variety.

The agent keeps out of a cycle. The environment ends a game whose position repeats as a
defeat of the side that repeated it, and the policy cannot see that from the observation:
a pickup and a drop each look like a fine command on their own. So the agent keeps the
position key of each state it decided in, applies its first choice on the engine, and when
the position it gives is one the agent has decided in before, it takes the next command by
score. The fourth 1 million step run lost 38 of 160 evaluation games that way, with the
argmax of a policy that had not closed. One `apply` for each decision is the cost.

Why this and not `ppo.choose`: `ppo.choose` needs a `SquadLeaderEnv` for its target mask, and
a real game outside the trainer has an engine, a state, and a frame, not an environment. The
board tensor and the unit tensor come from the same encoding functions the environment calls,
so the distribution the policy reads is the distribution it was trained on.

Torch is a heavy optional dependency (the `train` extra). It is imported inside the methods,
so importing this module never needs torch. A consumer that has no torch gets the typed error
at the boundary in `slcli.play`, and not here.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Mapping

from slagents.learned import encoding
from slagents.learned.encoding import position_key
from slcore.frame import DecisionFrame, LegalCommand
from slcore.game import State

if TYPE_CHECKING:  # pragma: no cover - types only, no runtime import
    from slcore.engine import Engine
    from slagents.learned.nets import Policy


class NoLegalCommand(RuntimeError):
    """The frame has no command. The engine always offers at least end_phase, so an empty
    frame is a defect in the caller and not a state the policy must handle."""


class SnapshotShapeError(ValueError):
    """The snapshot was trained on a board of a different size than the current engine."""


def load_policy(snapshot_path: Path) -> "Policy":
    """A policy of the shape the snapshot records, with the snapshot's weights.

    The snapshot holds the `spaces` and the `net` dictionaries next to the state dictionary
    (see `League.take_snapshot`). The trainer keeps a live `Policy` and calls `load_snapshot`
    on it, because it already has one of the right shape. A consumer that loads a snapshot on
    its own has no such policy, so it rebuilds the shape from the two dictionaries first, and
    then loads the same way the trainer does.
    """
    import torch

    from slagents.learned.league import load_snapshot
    from slagents.learned.nets import NetConfig, Policy

    saved = torch.load(snapshot_path, map_location="cpu", weights_only=False)
    if "spaces" not in saved or "net" not in saved:
        raise KeyError(
            f"the snapshot {snapshot_path} has no spaces or net record; it is not a training snapshot"
        )
    s = saved["spaces"]
    spaces = encoding.Spaces(
        units=int(s["units"]),
        actions=int(s["actions"]),
        targets=int(s["targets"]),
        cols=int(s["cols"]),
        rows=int(s["rows"]),
    )
    net = NetConfig(**{k: int(v) for k, v in saved["net"].items()})
    policy = Policy(spaces, net)
    load_snapshot(snapshot_path, policy)
    return policy


class LearnedAgent:
    """A trained PPO policy as a computer opponent (FR-51).

    The agent holds the engine's board and counter types, because the encoding functions read
    both and neither changes during a game. It builds one policy from the snapshot at
    construction, and it reads the same policy in each decision.
    """

    name = "learned"
    version = "0.1"

    def __init__(
        self,
        engine: "Engine",
        snapshot_path: str | Path | None,
        seed: int | None = None,
        policy: "Policy | None" = None,
    ) -> None:
        if policy is None:
            if snapshot_path is None:
                raise ValueError("a learned agent needs a snapshot path or a policy")
            policy = load_policy(Path(snapshot_path))
        self.snapshot_path = Path(snapshot_path) if snapshot_path is not None else None
        self.engine = engine
        self.board = engine.board
        self.types = engine.types
        self.policy = policy
        self.spaces = self.policy.spaces
        self._seen: set[str] = set()
        self._last_seq = -1
        if (self.spaces.cols, self.spaces.rows) != (self.board.cols, self.board.rows):
            raise SnapshotShapeError(
                f"the snapshot board is {self.spaces.cols}x{self.spaces.rows} and the engine board is "
                f"{self.board.cols}x{self.board.rows}; the snapshot must be trained on this scenario"
            )
        self.hexes = encoding.hex_slots(self.board)
        self._generator = None
        if seed is not None:
            import torch

            self._generator = torch.Generator().manual_seed(int(seed))

    @classmethod
    def from_policy(cls, engine: "Engine", policy: "Policy", seed: int | None = None) -> "LearnedAgent":
        """The agent around a policy that is already in memory, on whatever device it holds.

        The trainer's evaluation reads the policy it trained through this, so the number
        of TC-18 is the number of the agent that a tournament plays, and not of a second
        selection rule.
        """
        return cls(engine, None, seed, policy=policy)

    def select(self, state: State, frame: DecisionFrame) -> str:
        """The ID of the best legal command, by the policy's three heads.

        A tie between two legal commands with the same three parts is broken by the lowest
        command ID, which `group_commands` already does. A tie between two triples with the
        same score is broken by the lowest triple, because the loop reads the triples in
        ascending order and keeps the first of an equal score.
        """
        if not frame.commands:
            raise NoLegalCommand(
                f"the frame in {frame.phase}/{frame.sub_step} has no command; the engine always offers end_phase"
            )
        import torch

        self._remember(state)
        player = frame.player
        groups = encoding.group_commands(frame, self.hexes)
        device = next(self.policy.parameters()).device
        board = torch.from_numpy(
            encoding.board_tensor(self.board, state, self.types, player, self.spaces)
        ).unsqueeze(0).to(device)
        units = torch.from_numpy(
            encoding.unit_tensor(state, self.types, player, self.spaces, self.board)
        ).unsqueeze(0).to(device)
        scalars = torch.from_numpy(encoding.scalar_vector(state, frame, player)).unsqueeze(0).to(device)
        with torch.no_grad():
            trunk, unit_embeddings = self.policy.encode(board, units, scalars)
            scores = self._scores(trunk, unit_embeddings, groups, torch, device)
        ordered = self._by_score(scores, groups)
        if self._generator is not None:
            first = self._sample(scores, groups, torch)
            ordered = [first] + [c for c in ordered if c is not first]
        return self._first_that_does_not_repeat(state, frame, ordered).id

    # ---------------------------------------------------------------- inside

    def _remember(self, state: State) -> None:
        """The positions this agent decided in, for the current game only."""
        if state.seq < self._last_seq:
            self._seen.clear()
        self._last_seq = state.seq
        self._seen.add(position_key(state))

    def _first_that_does_not_repeat(self, state: State, frame: DecisionFrame, ordered: list[LegalCommand]) -> LegalCommand:
        """The first command of the order whose position the agent has not decided in.

        The first choice costs one `apply`. A choice that repeats costs one more for the
        next. When each legal command repeats, which the last command of a cycle can force,
        the first choice stands and the environment gives its verdict.
        """
        for choice in ordered:
            after, _ = self.engine.apply(state, choice.command, frame)
            if position_key(after) not in self._seen:
                return choice
        return ordered[0]

    @staticmethod
    def _by_score(scores: dict[tuple[int, int, int], float], groups) -> list[LegalCommand]:
        """The legal commands from the highest score down, with the lowest triple as the tie break."""
        return [groups[triple] for triple in sorted(scores, key=lambda t: (-scores[t], t))]

    def _scores(self, trunk, unit_embeddings, groups: Mapping[tuple[int, int, int], LegalCommand], torch, device) -> dict[tuple[int, int, int], float]:
        """The composed log probability of each legal triple.

        The unit head is read once. The action head is read once for each legal unit slot, and
        the target head once for each legal unit and action. So the whole set is scored with a
        few forward calls, and not one for each command.
        """
        unit_mask = torch.zeros(self.spaces.units, dtype=torch.float32, device=device)
        for u, _, _ in groups:
            unit_mask[u] = 1.0
        u_logits = self.policy.unit_logits(trunk, unit_embeddings, unit_mask.unsqueeze(0))
        u_logp = torch.log_softmax(u_logits.squeeze(0), dim=-1)

        action_logp: dict[int, object] = {}
        target_logp: dict[tuple[int, int], object] = {}
        scores: dict[tuple[int, int, int], float] = {}
        for triple in sorted(groups):
            unit, action, target = triple
            if unit not in action_logp:
                a_mask = torch.zeros(self.spaces.actions, dtype=torch.float32, device=device)
                for u2, a2, _ in groups:
                    if u2 == unit:
                        a_mask[a2] = 1.0
                a_logits = self.policy.action_logits(
                    trunk,
                    unit_embeddings,
                    torch.tensor([unit], dtype=torch.long, device=device),
                    a_mask.unsqueeze(0),
                )
                action_logp[unit] = torch.log_softmax(a_logits.squeeze(0), dim=-1)
            key = (unit, action)
            if key not in target_logp:
                t_mask = torch.zeros(self.spaces.targets, dtype=torch.float32, device=device)
                for u2, a2, t2 in groups:
                    if u2 == unit and a2 == action:
                        t_mask[t2] = 1.0
                t_logits = self.policy.target_logits(
                    trunk,
                    unit_embeddings,
                    torch.tensor([unit], dtype=torch.long, device=device),
                    torch.tensor([action], dtype=torch.long, device=device),
                    t_mask.unsqueeze(0),
                )
                target_logp[key] = torch.log_softmax(t_logits.squeeze(0), dim=-1)
            scores[triple] = float(
                u_logp[unit].item() + action_logp[unit][action].item() + target_logp[key][target].item()
            )
        return scores

    def _sample(self, scores: dict[tuple[int, int, int], float], groups, torch) -> LegalCommand:
        """A seeded draw over the legal triples, weighted by the composed log probability.

        The composed score of each legal triple is a log probability, so the softmax over the
        scores is a distribution over the legal commands. The seed makes the draw reproducible.
        """
        ordered = sorted(scores)
        weights = torch.softmax(torch.tensor([scores[t] for t in ordered], dtype=torch.float32), dim=-1)
        index = int(torch.multinomial(weights, 1, generator=self._generator).item())
        return groups[ordered[index]]
