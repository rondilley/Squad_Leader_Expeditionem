"""The trained policy as a normal computer opponent (FR-51, FR-52).

A snapshot from `sl-cli train` is a policy that only the training environment could drive.
This wrapper gives it the Agent interface, so it plays in a tournament, a gate, and a real
game the same way a scripted agent does.

The wrapper scores the legal commands that the core offers and returns the ID of the best
one. It does not sample a key and hope the key is legal: it reads `frame.commands`,
maps each legal command to its four parts with the same `group_commands` the trainer uses,
and scores each key with the policy's four heads. So the returned ID is always a real
legal command, and the target mask does not have to be rebuilt outside the environment.

The score of a command is the sum of the four per-head log probabilities, which is how
`ppo.choose` composes the log probability of a whole command. The default choice is
deterministic, because a tournament and a replay must give the same command for the same
state. A seed turns on sampling over the scores for a run that wants variety.

The default choice is the action first. The probability of each action is the sum of the
probabilities of its legal commands, and the agent plays the best command of the action
with the highest sum. The argmax of the joint score was the rule before 2026-10-13, and it
does not work for this action space: the policy divides the probability of an infantry
move between many units and hexes, and the probability of `end_phase` stays on one
command. In the s04 Movement Phase the policy gave `move` 0.66 over 30 commands and
`end_phase` 0.23, and the argmax played `end_phase`. The clone of v7 made no infantry move
in a whole game and won 0 of 10 attacks against random; with the action first it won 6 of
10 (docs/reports/2026-10-13_training_review.md).

The Prep Fire Phase is the exception (`JOINT_SCORE_PHASES`, 2026-10-27). There the sum works
the wrong way: each unit that can fire adds to the sum of a fire action, and the end of the
phase stays on one command. At the first Prep Fire frame of a turn the L05 teacher ended the
phase in 65 of 84 frames, and the clone's joint argmax agreed with it in 78.6 percent; but
it gave the end of the phase 0.31, so the action first fired in each one, and the units that
fired did not move (`runs/exam_20261021_prep_fire/share.py`). In that phase the agent plays
the command of the highest joint score.

A route and a stack route are one action in the sum (`ACTION_FAMILY`, 2026-10-27). With two
sums the single route won each time, because each unit has single routes and only a stack
has stack routes. On L05 the leaders went forward alone and left the squads of their stacks
behind: 5 stack moves in each game, against 19 of the teacher. With one sum the v7 gate of
200 games gave the defence of L04 93 of 100 (was 52) and of L05 74 of 100 (was 7), and the
attack did not change (L03 44, L04 15, L05 0 of 100).

The agent keeps out of a cycle. The environment ends a game whose position repeats as a
defeat of the side that repeated it, and the policy cannot see that from the observation:
a pickup and a drop each look like a fine command on their own. So the agent keeps the
position key of each state it decided in, applies its first choice on the engine, and when
the position it gives is one the agent has decided in before, it takes the next command by
score. The fourth 1 million step run lost 38 of 160 evaluation games that way, with the
argmax of a policy that had not closed. One `apply` for each decision is the cost.

A repeat is not the only cycle. A pickup and a drop cost no movement factor (rule 5.7), so
a policy that likes them can hand a few weapons between a few units and give a new set of
holders at each step. The guard then walks through the sets, which are a power of the
weapon count: the scenario 2 net played 5,000 commands of one Movement Phase that way, and
five gauntlet games did not end in 20,000 commands (2026-10-12). So the agent also keeps
the weapons it picked up or dropped in the current phase, and a second pickup or drop of
one of them goes after each other command. The phase then has at most two such commands
for each weapon. A board and a debark are the same kind of loop: a squad got on a tank and
off it 250 times in one phase (2026-10-13), because the core does not stop a unit that
debarked from boarding again. So a second board or debark of one unit in a phase also
goes after each other command. This is an order of preference, not a rule: the legal
list is the core's.

A move back is a cycle that the repeat guard does not find, because each step uses a
movement factor and so gives a new position: the L02 clone moved one squad eight times
between two hexes in one phase (2026-10-20). So a move of a unit into a hex that it held in
the phase also goes after each other command (`routes.PhaseMemory`).

A net with the route actions (`routes.uses_routes`) selects a destination for a unit or a
stack in the Movement Phase, in place of its single steps. The agent gives the first step,
and at each next decision of the phase it gives the next step of the route with no call of
the net, while the frame offers that step. Then the net selects again
(`docs/reports/2026-10-20_attack_movement_design.md`). Each route key has its own copy of
the legal command of its first step, so the order methods read legal commands as before,
and the agent knows which route a chosen copy starts.

Why this and not `ppo.choose`: `ppo.choose` needs a `SquadLeaderEnv` for its target mask, and
a real game outside the trainer has an engine, a state, and a frame, not an environment. The
board tensor and the unit tensor come from the same encoding functions the environment calls,
so the distribution the policy reads is the distribution it was trained on.

Torch is a heavy optional dependency (the `train` extra). It is imported inside the methods,
so importing this module never needs torch. A consumer that has no torch gets the typed error
at the boundary in `slagents.registry`, and not here.
"""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

from slagents.learned import encoding, routes
from slagents.learned.encoding import position_key
from slcore.engine import IllegalCommand
from slcore.frame import DecisionFrame, LegalCommand
from slcore.game import State
from slcore.player_state import for_player

if TYPE_CHECKING:  # pragma: no cover - types only, no runtime import
    from slcore.engine import Engine
    from slagents.learned.nets import Policy


# The commands that hand a weapon from one unit to another at no movement cost (rule 5.7).
WEAPON_ACTIONS = frozenset({"pickup", "drop"})

# The commands that put a unit on a vehicle and take it off (rules 31.1 and 31.4).
RIDE_ACTIONS = frozenset({"board", "debark"})

# The phases where the agent plays the command of the highest joint score, not the action
# first. In the Prep Fire Phase the sum of a fire action over each unit that can fire is
# larger than the end of the phase, and a unit that fires does not move (rules 4.3 and 5.1).
JOINT_SCORE_PHASES = frozenset({"prep_fire"})

# The actions that share one sum in the action first: a stack route is the move of a unit
# with the units of its stack. Each unit has single routes, and only a stack has stack
# routes, so with two sums the single route won each time, and a leader went on alone.
ACTION_FAMILY = {encoding.ACTION_INDEX["stack_route"]: encoding.ACTION_INDEX["route"]}


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

    saved = torch.load(snapshot_path, map_location="cpu", weights_only=True)
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
        options=int(s["options"]) if "options" in s else encoding.MAX_OPTIONS,
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
        self._handled: set[int] = set()
        self._rode: set[int] = set()
        self._handled_phase: tuple[int, str, int] | None = None
        self.uses_routes = routes.uses_routes(self.spaces)
        self._memory = routes.PhaseMemory()
        # The route in progress: the route, the steps it played, and its phase.
        self._plan: tuple[routes.Route, int, tuple[int, str, int]] | None = None
        # The route of each copy of a first step, by the identity of the copy.
        self._route_of: dict[int, routes.Route] = {}
        if (self.spaces.cols, self.spaces.rows) != (self.board.cols, self.board.rows):
            raise SnapshotShapeError(
                f"the snapshot board is {self.spaces.cols}x{self.spaces.rows} and the engine board is "
                f"{self.board.cols}x{self.board.rows}; the snapshot must be trained on this scenario"
            )
        self.hexes = encoding.hex_slots(self.board)
        self.objectives = encoding.objectives_for(engine)
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
        """The ID of the best legal command, by the policy's four heads, action first.

        A tie between two legal commands with the same three parts is broken by the lowest
        command ID, which `group_commands` already does. A tie between two keys with the
        same score is broken by the lowest key.
        """
        if not frame.commands:
            raise NoLegalCommand(
                f"the frame in {frame.phase}/{frame.sub_step} has no command; the engine always offers end_phase"
            )
        import torch

        player = frame.player
        self._remember(state, player)
        self._memory.update(state, player)
        step = self._next_route_step(state, frame, player)
        if step is not None:
            return step.id
        groups = encoding.group_commands(frame, self.hexes)
        self._route_of = {}
        if self.uses_routes:
            table = routes.route_table(self.engine, state, frame, self.hexes, self._memory)
            if table:
                groups = routes.with_routes(groups, table)
                for key, (route, first) in table.items():
                    groups[key] = copy.copy(first)
                    self._route_of[id(groups[key])] = route
        device = next(self.policy.parameters()).device
        board = torch.from_numpy(
            encoding.board_tensor(self.board, state, self.types, player, self.spaces, self.objectives)
        ).unsqueeze(0).to(device)
        units = torch.from_numpy(
            encoding.unit_tensor(state, self.types, player, self.spaces, self.board, sorted({u for u, _, _, _ in groups}))
        ).unsqueeze(0).to(device)
        scalars = torch.from_numpy(encoding.scalar_vector(state, frame, player)).unsqueeze(0).to(device)
        with torch.no_grad():
            trunk, unit_embeddings = self.policy.encode(board, units, scalars)
            scores = self._scores(trunk, unit_embeddings, groups, torch, device)
        if frame.phase in JOINT_SCORE_PHASES:
            ordered = self._by_joint_score(scores, groups)
        else:
            ordered = self._by_score(scores, groups)
        if self._generator is not None:
            first = self._sample(scores, groups, torch)
            ordered = [first] + [c for c in ordered if c is not first]
        ordered = self._weapons_handled_last(state, ordered, player)
        ordered = self._rides_handled_last(ordered)
        ordered = self._returns_last(ordered)
        choice = self._first_that_does_not_repeat(state, frame, ordered, player)
        if choice.command.action in WEAPON_ACTIONS and choice.command.weapon is not None:
            self._handled.add(choice.command.weapon)
        if choice.command.action in RIDE_ACTIONS:
            self._rode.update(choice.command.units)
        route = self._route_of.get(id(choice))
        if route is not None:
            self._plan = (route, 1, (state.turn, state.phase, player))
        return choice.id

    # ---------------------------------------------------------------- inside

    @staticmethod
    def _view_key(state: State, player: int) -> str:
        """The position as this player may know it (S13, S3).

        A key of the full state would let the choice depend on what the player cannot
        see: two commands with the same view and a different hidden unit or a different
        generator state would be one repeat and one new position.
        """
        return position_key(for_player(state, player))

    def _remember(self, state: State, player: int) -> None:
        """The positions this agent decided in, for the current game only."""
        if state.seq < self._last_seq:
            self._seen.clear()
            self._handled.clear()
            self._rode.clear()
            self._handled_phase = None
            self._memory.clear()
            self._plan = None
        self._last_seq = state.seq
        self._seen.add(self._view_key(state, player))

    def _next_route_step(self, state: State, frame: DecisionFrame, player: int) -> LegalCommand | None:
        """The next step of the route in progress, or None when the route ended."""
        if self._plan is None:
            return None
        route, done, phase = self._plan
        step = None
        if phase == (state.turn, state.phase, player):
            step = routes.next_step(route, done, state, frame)
        self._plan = (route, done + 1, phase) if step is not None else None
        return step

    def _returns_last(self, ordered: list[LegalCommand]) -> list[LegalCommand]:
        """The order with each move into a hex that its unit held in the phase at the end.

        A route is not a return when its first step crosses a held hex: the route table
        already leaves out each route to a held destination.
        """
        back = [c for c in ordered if id(c) not in self._route_of and self._memory.returns(c.command)]
        if not back:
            return ordered
        last = {id(c) for c in back}
        return [c for c in ordered if id(c) not in last] + back

    def _weapons_handled_last(self, state: State, ordered: list[LegalCommand], player: int) -> list[LegalCommand]:
        """The order with each pickup and drop of a weapon handled in this phase at the end."""
        phase = (state.turn, state.phase, player)
        if phase != self._handled_phase:
            self._handled.clear()
            self._rode.clear()
            self._handled_phase = phase
        if not self._handled:
            return ordered
        again = {c.id for c in ordered if c.command.action in WEAPON_ACTIONS and c.command.weapon in self._handled}
        if not again:
            return ordered
        return [c for c in ordered if c.id not in again] + [c for c in ordered if c.id in again]

    def _rides_handled_last(self, ordered: list[LegalCommand]) -> list[LegalCommand]:
        """The order with each board and debark of a unit that rode in this phase at the end.

        `_weapons_handled_last` runs first and clears the set at a new phase.
        """
        if not self._rode:
            return ordered
        again = {c.id for c in ordered if c.command.action in RIDE_ACTIONS and self._rode.intersection(c.command.units)}
        if not again:
            return ordered
        return [c for c in ordered if c.id not in again] + [c for c in ordered if c.id in again]

    def _first_that_does_not_repeat(self, state: State, frame: DecisionFrame, ordered: list[LegalCommand], player: int) -> LegalCommand:
        """The first command of the order whose position the agent has not decided in.

        The first choice costs one `apply`. A choice that repeats costs one more for the
        next. When each legal command repeats, which the last command of a cycle can force,
        the first choice stands and the environment gives its verdict.
        """
        own = self.engine.legal_commands(state)
        repeats: set[str] = set()
        for choice in ordered:
            if choice.id in repeats:
                # Two routes with the same first step give the same position after it.
                continue
            try:
                after, _ = self.engine.apply(state, choice.command, own)
            except IllegalCommand:
                # The state here is the player state, with no enemy unit that the view
                # hides. A command of the true list that this state does not offer has no
                # lookahead, and the choice stands.
                return choice
            if self._view_key(after, player) not in self._seen:
                return choice
            repeats.add(choice.id)
        return ordered[0]

    @staticmethod
    def _by_score(scores: dict[tuple[int, int, int, int], float], groups) -> list[LegalCommand]:
        """The legal commands action first: the action with the highest sum of probability
        over its legal commands, then each command of that action from the highest score
        down, then the next action. The lowest key breaks a tie.

        The second part of a key is the index of the action in the encoding, the same for
        each unit, so the sum is over each unit and hex of that action. The actions of one
        family (`ACTION_FAMILY`) share one sum.
        """
        mass: dict[int, float] = {}
        for key, score in scores.items():
            action = ACTION_FAMILY.get(key[1], key[1])
            mass[action] = mass.get(action, 0.0) + math.exp(score)
        return [
            groups[key]
            for key in sorted(scores, key=lambda t: (-mass[ACTION_FAMILY.get(t[1], t[1])], -scores[t], t))
        ]

    @staticmethod
    def _by_joint_score(scores: dict[tuple[int, int, int, int], float], groups) -> list[LegalCommand]:
        """The legal commands from the highest joint score down. The lowest key breaks a tie."""
        return [groups[key] for key in sorted(scores, key=lambda t: (-scores[t], t))]

    def _scores(self, trunk, unit_embeddings, groups: Mapping[tuple[int, int, int, int], LegalCommand], torch, device) -> dict[tuple[int, int, int, int], float]:
        """The composed log probability of each legal command.

        Four forward calls score the whole set: the unit head once, the action head once
        for all the legal unit slots as one batch, the target head once for all the legal
        unit and action pairs, and the option head once for all the legal unit, action,
        and hex triples. The log probabilities come to the processor once.
        """
        import numpy as np

        spaces = self.spaces
        quads = sorted(groups)
        units = sorted({u for u, _, _, _ in quads})
        pairs = sorted({(u, a) for u, a, _, _ in quads})
        aimed = sorted({(u, a, t) for u, a, t, _ in quads})
        unit_index = {u: i for i, u in enumerate(units)}
        pair_index = {pair: i for i, pair in enumerate(pairs)}
        aim_index = {aim: i for i, aim in enumerate(aimed)}
        unit_mask = np.zeros(spaces.units, dtype=np.float32)
        action_mask = np.zeros((len(units), spaces.actions), dtype=np.float32)
        target_mask = np.zeros((len(pairs), spaces.targets), dtype=np.float32)
        option_mask = np.zeros((len(aimed), spaces.options), dtype=np.float32)
        for u, a, t, o in quads:
            unit_mask[u] = 1.0
            action_mask[unit_index[u], a] = 1.0
            target_mask[pair_index[(u, a)], t] = 1.0
            option_mask[aim_index[(u, a, t)], o] = 1.0
        u_logits = self.policy.unit_logits(trunk, unit_embeddings, torch.from_numpy(unit_mask).unsqueeze(0).to(device))
        u_logp = torch.log_softmax(u_logits.squeeze(0), dim=-1).cpu().numpy()
        n = len(units)
        a_logits = self.policy.action_logits(
            trunk.expand(n, -1),
            unit_embeddings.expand(n, -1, -1),
            torch.tensor(units, dtype=torch.long, device=device),
            torch.from_numpy(action_mask).to(device),
        )
        a_logp = torch.log_softmax(a_logits, dim=-1).cpu().numpy()
        m = len(pairs)
        t_logits = self.policy.target_logits(
            trunk.expand(m, -1),
            unit_embeddings.expand(m, -1, -1),
            torch.tensor([u for u, _ in pairs], dtype=torch.long, device=device),
            torch.tensor([a for _, a in pairs], dtype=torch.long, device=device),
            torch.from_numpy(target_mask).to(device),
        )
        t_logp = torch.log_softmax(t_logits, dim=-1).cpu().numpy()
        p = len(aimed)
        o_logits = self.policy.option_logits(
            trunk.expand(p, -1),
            unit_embeddings.expand(p, -1, -1),
            torch.tensor([u for u, _, _ in aimed], dtype=torch.long, device=device),
            torch.tensor([a for _, a, _ in aimed], dtype=torch.long, device=device),
            torch.tensor([t for _, _, t in aimed], dtype=torch.long, device=device),
            torch.from_numpy(option_mask).to(device),
        )
        o_logp = torch.log_softmax(o_logits, dim=-1).cpu().numpy()
        return {
            (u, a, t, o): float(
                u_logp[u]
                + a_logp[unit_index[u], a]
                + t_logp[pair_index[(u, a)], t]
                + o_logp[aim_index[(u, a, t)], o]
            )
            for u, a, t, o in quads
        }

    def _sample(self, scores: dict[tuple[int, int, int, int], float], groups, torch) -> LegalCommand:
        """A seeded draw over the legal commands, weighted by the composed log probability.

        The composed score of each legal command is a log probability, so the softmax over the
        scores is a distribution over the legal commands. The seed makes the draw reproducible.
        """
        ordered = sorted(scores)
        weights = torch.softmax(torch.tensor([scores[t] for t in ordered], dtype=torch.float32), dim=-1)
        index = int(torch.multinomial(weights, 1, generator=self._generator).item())
        return groups[ordered[index]]
