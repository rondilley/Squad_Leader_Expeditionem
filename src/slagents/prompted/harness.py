"""The model agent harness (FR-45 to FR-49, FR-59, SR-04, SR-09).

The harness is the fourth agent family behind the same interface as the others: it gets a
state and a frame, and it gives back one command identity. What it does between those two
is:

1. Build a text state from the acting player's view and from nothing else (FR-45, SR-09).
   The text has the units the player may see, the terrain of the hexes that matter, the
   victory conditions of the card, and the legal command list with an identity for each
   command. Each command carries its odds from the tables of the core (`oddsview`): the
   result and break chances of a shot, the break chance of a move, the kill chances of a
   close combat, the chance of a rally. A model reads a number where the scripted agent
   reads the same number.
2. Send the text to a provider and let the model write its analysis in free text first,
   then one JSON object that a flat schema constrains (FR-46).
3. When the object does not satisfy the schema, or its command identity is not in the
   list, send the rejection message back and ask again, up to a count (FR-47).
4. After the last failure, take the command that the scripted agent would take, and record
   the fallback (FR-47).

Three things the harness never does. It never sends an image (FR-48). It never runs the
model output: the output is a command identity that the harness looks up in the frame the
core gave (SR-04). It never puts a key in a log line or an artifact (SR-01).

The cycle guard. A model that may drop a weapon and pick it up again does so for hours:
one game of the gauntlet of 2026-09-19 had 15,837 decisions against 120 to 274 for the
others. So the harness keeps the positions of the game it has seen in the phase, and it
offers the model no command that returns the game to one of them. A position is the
view document of the acting player, with the step (S13). The harness finds the position a command
gives with the core's own `apply` on the state, which changes nothing, and the list the
model reads is the legal list less those commands. When each command returns, the guard
stands down and the full list goes out.

The harness records the four rates that TC-16 asks for: invalid commands, retries,
fallbacks, and timeouts. FR-59 says that a model with a median decision time above five
seconds is an asynchronous opponent, so the harness records each decision time and says
which side of that line it is on.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from slagents.base import decide
from slagents.prompted import schema
from slagents.prompted.oddsview import OddsView, objective_lines
from slagents.prompted.providers import Answer, Provider, ProviderError, ProviderUnavailable
from slcore import geometry
from slcore.engine import Engine, IllegalCommand
from slcore.frame import DecisionFrame, LegalCommand
from slcore.game import State
from slcore.los_eval import evaluate as evaluate_los
from slcore.view import build as build_view, visible_to

ASYNCHRONOUS_SECONDS = 5.0
DEFAULT_RETRIES = 2
MAX_COMMANDS_IN_PROMPT = 120
MAX_PLANS = 3
NEAREST_ENEMIES = 4

SYSTEM_PROMPT = (
    "You command one side in a tactical infantry game on a hex board. You get the state "
    "that your side can see and the list of legal commands. You select one command from "
    "that list. You never invent a command, and you never name a hex that is not in the "
    "list. Each command carries its odds from the tables of the game: for a shot, the "
    "chance of a result and the chance that each unit in the target breaks; for a move, "
    "the chance that the mover breaks under the enemy fire that can reach it; for a close "
    "combat, the kill chance of each side; for a rally, the chance it holds. A missing "
    "number is unknown, not zero. Put the fire of many units on one target until its "
    "break chance is high, then the next target. Move under cover toward the objective, "
    "and cross open ground only when the break chance is low or the objective needs it. "
    "Keep a leader with the squads, and rally the broken. Write a short analysis first, "
    "then one JSON object."
)


@dataclass
class Counters:
    """What TC-16 and OR-02 ask a run to record."""

    decisions: int = 0
    calls: int = 0
    invalid: int = 0
    retries: int = 0
    fallbacks: int = 0
    timeouts: int = 0
    provider_errors: int = 0
    refused: int = 0  # the decisions where the cycle guard held one command back or more
    refused_commands: int = 0  # the commands it held back, in total
    seconds: list[float] = field(default_factory=list)

    def rate(self, count: int) -> float:
        return 0.0 if self.decisions == 0 else count / self.decisions

    def to_dict(self) -> dict[str, Any]:
        median = statistics.median(self.seconds) if self.seconds else 0.0
        return {
            "decisions": self.decisions,
            "calls": self.calls,
            "invalid_commands": self.invalid,
            "invalid_rate": round(self.rate(self.invalid), 4),
            "retries": self.retries,
            "retry_rate": round(self.rate(self.retries), 4),
            "fallbacks": self.fallbacks,
            "fallback_rate": round(self.rate(self.fallbacks), 4),
            "timeouts": self.timeouts,
            "timeout_rate": round(self.rate(self.timeouts), 4),
            "provider_errors": self.provider_errors,
            "refused": self.refused,
            "refused_rate": round(self.rate(self.refused), 4),
            "refused_commands": self.refused_commands,
            "median_seconds": round(median, 3),
            "max_seconds": round(max(self.seconds), 3) if self.seconds else 0.0,
            "asynchronous": median > ASYNCHRONOUS_SECONDS,
        }


def position_key(state: State, types: Any, viewer: int) -> str:
    """The position of the game as the acting player sees it: that player's view, and the step.

    The state hash of the core (FR-13) counts each command, so a drop and a pickup give a
    new hash and the same position. The guard compares positions.

    The key is the view document of the player (`slcore.view.build`), with the sub-step,
    and not the full state (S13). A key of the full state lets the list the model reads
    depend on what the player cannot see: two commands that give the same view and a
    different hidden unit would be one repeat and one new position, and the held count in
    the prompt would tell the model which one moved a hidden unit (SR-09).
    """
    document = build_view(state, types, viewer)
    document["sub_step"] = state.sub_step
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


def hex_line(engine: Engine, state: State, hex_ref, viewer: int) -> str:
    """One hex of the text state: its terrain and what it holds."""
    h = engine.board.hex(hex_ref)
    parts = [h.id, h.terrain]
    if h.building is not None:
        parts.append(f"building {h.building.id}")
    if h.road:
        parts.append("road")
    if h.sewer:
        parts.append("sewer entrance")
    return " ".join(parts)


def nearest_enemies(engine: Engine, state: State, unit, viewer: int) -> list[str]:
    """The enemy hexes this unit can see, nearest first, with the line of sight answer."""
    if unit.hex is None:
        return []
    out: list[tuple[int, str]] = []
    for other in state.units:
        if other.eliminated or other.player == viewer or other.hex is None or other.carrier is not None:
            continue
        if not visible_to(state, other, viewer):
            continue
        distance = geometry.distance(unit.hex, other.hex)
        clear = evaluate_los(engine.board, engine.los, unit.hex, other.hex).clear
        out.append((distance, f"{geometry.hex_id(*other.hex)} at {distance} hexes, line of sight {'clear' if clear else 'blocked'}"))
    out.sort()
    seen: list[str] = []
    for _, text in out:
        if text not in seen:
            seen.append(text)
        if len(seen) >= NEAREST_ENEMIES:
            break
    return seen


def text_state(
    engine: Engine,
    state: State,
    frame: DecisionFrame,
    viewer: int,
    plans: Sequence[str],
    commands: Sequence[LegalCommand] | None = None,
) -> str:
    """The compact text of FR-45, from the acting player's view alone (SR-09).

    `commands` is the list the model may take, when the cycle guard held some back. The
    default is the legal list of the frame.
    """
    offered = list(frame.commands) if commands is None else list(commands)
    document = build_view(state, engine.types, viewer)
    side = engine.scenario.players()[viewer]
    view = OddsView(engine, state, viewer)
    lines = [
        f"Scenario {engine.scenario.id}. You are the {side} side, player {viewer}.",
        f"Turn {document['turn']} of {document['turn_limit']}. Phase {document['phase']}, step {frame.sub_step}.",
        "",
    ]
    lines.extend(objective_lines(engine, state, viewer))
    lines.append("")
    lines.append("Your units (the break chance is under the enemy fire you can see):")
    own = [u for u in document["units"] if u["own"] and u["hex"] is not None]
    for unit in sorted(own, key=lambda u: u["id"]):
        marks = [name for name in ("broken", "moved", "prep_fired", "dm", "berserk", "malfunction") if unit[name]]
        state_text = f" [{', '.join(marks)}]" if marks else ""
        where = unit["hex"]
        hex_ref = geometry.parse_hex_id(where)
        note = view.unit_note(state.units[unit["id"]])
        lines.append(
            f"  {unit['id']}: {unit['type']}{' ' + unit['name'] if unit['name'] else ''} in {where} ({view.terrain(hex_ref)}), "
            f"morale {unit['morale']}{state_text}{', ' + note if note else ''}"
        )
    lines.append("")
    lines.append("Enemy units you can see:")
    other = [u for u in document["units"] if not u["own"] and u["hex"] is not None]
    if not other:
        lines.append("  none")
    for unit in sorted(other, key=lambda u: u["id"]):
        hex_ref = geometry.parse_hex_id(unit["hex"])
        lines.append(f"  {unit['id']}: {unit['type']} in {unit['hex']} ({view.terrain(hex_ref)}), morale {unit['morale']}")
    counters = {c["hex"]: c for c in document["concealment"]}
    if counters:
        lines.append("")
        lines.append("Concealment counters (a counter can hide a stack or nothing):")
        for hex_id, counter in sorted(counters.items()):
            lines.append(f"  {hex_id}: {counter['stack']} counter(s){' of your side' if counter['own'] else ''}")
    if document["smoke"]:
        lines.append("")
        lines.append("Smoke: " + ", ".join(sorted(document["smoke"])))
    first = own[0] if own else None
    if first is not None:
        unit = state.units[first["id"]]
        seen = nearest_enemies(engine, state, unit, viewer)
        if seen:
            lines.append("")
            lines.append(f"From {first['hex']}: " + "; ".join(seen))
    if plans:
        lines.append("")
        lines.append("Your last plans:")
        for plan in plans:
            lines.append(f"  {plan}")
    lines.append("")
    lines.append("Legal commands, each with its odds. Answer with one of these identities:")
    shown = shown_commands(offered)
    for legal in shown:
        note = view.command_note(legal)
        lines.append(f"  {legal.id} {command_text(engine, legal.payload)}{' -> ' + note if note else ''}")
    if len(offered) > len(shown):
        lines.append(f"  ... and {len(offered) - len(shown)} more of the same kinds")
    held = len(frame.commands) - len(offered)
    if held > 0:
        lines.append(f"  ({held} command{'s' if held != 1 else ''} that would return the game to a position of this phase are not offered.)")
    lines.append("")
    lines.append(schema.describe([lc.id for lc in offered]))
    return "\n".join(lines)


# The commands that end a phase or the set up. The model always sees them (L6).
ENDING_ACTIONS = ("end_phase", "end_setup")


def shown_commands(offered: Sequence[LegalCommand]) -> list[LegalCommand]:
    """The commands the prompt lists: the first ones up to the limit, and each ending command.

    The core puts `end_phase` last in a frame. A Movement Phase of a large force has more
    than `MAX_COMMANDS_IN_PROMPT` commands, and the cut then took the one command that
    ends the phase out of the list the model reads, so the model could not end the phase
    (the review of 2026-09-23, L6). The ending commands now take their places at the end
    of the list, and the cut takes that many fewer of the others.
    """
    ending = [lc for lc in offered if lc.command.action in ENDING_ACTIONS]
    if len(offered) <= MAX_COMMANDS_IN_PROMPT:
        return list(offered)
    room = max(0, MAX_COMMANDS_IN_PROMPT - len(ending))
    others = [lc for lc in offered if lc.command.action not in ENDING_ACTIONS][:room]
    return others + ending


def command_text(engine: Engine, payload: dict[str, Any]) -> str:
    """One legal command in words, so the model reads a move and not a record."""
    action = payload.get("action", "")
    units = payload.get("units") or []
    hex_id = payload.get("hex")
    weapon = payload.get("weapon")
    parts = [action]
    if units:
        parts.append("unit " + ",".join(str(u) for u in units))
    if weapon is not None:
        parts.append(f"weapon {weapon}")
    if hex_id:
        parts.append(f"hex {hex_id}")
    return " ".join(parts)


class PromptedAgent:
    """The model agent (FR-43): one state and one frame in, one command identity out."""

    name = "prompted"

    def __init__(
        self,
        engine: Engine,
        player: int,
        provider: Provider,
        default_agent: Any,
        retries: int = DEFAULT_RETRIES,
        max_tokens: int = 700,
        constrained: bool = False,
    ) -> None:
        self.engine = engine
        self.player = player
        self.provider = provider
        self.default_agent = default_agent
        self.retries = retries
        self.max_tokens = max_tokens
        # FR-62: with the constraint on, the provider holds the model to the schema, and
        # the invalid rate then measures the grammar and not the model.
        self.constrained = constrained and provider.supports_constraint()
        self.counters = Counters()
        self.plans: list[str] = []
        self.log: list[dict[str, Any]] = []
        self.version = f"{provider.name}:{provider.model}"
        # The cycle guard: the positions seen in the phase, and the phase they belong to.
        self._window: tuple[int, str] | None = None
        self._seen: set[str] = set()

    def offered(self, state: State, frame: DecisionFrame) -> tuple[list[LegalCommand], list[str]]:
        """The commands the model may take, and the identities the cycle guard held back.

        The guard forgets its positions when the turn or the phase changes, and it records
        the position of each state it decides on. A command that gives a position it
        recorded is held back. When each command does, the guard stands down.
        """
        window = (state.turn, state.phase)
        if window != self._window:
            self._window = window
            self._seen = set()
        self._seen.add(position_key(state, self.engine.types, self.player))
        if len(frame.commands) <= 1:
            return list(frame.commands), []
        kept: list[LegalCommand] = []
        held: list[str] = []
        # The state is the player state (S3), so its own legal list is built one time here
        # and each lookahead reads it. A command of the true list that the player state
        # does not offer has no lookahead, and it stays in the list.
        own = self.engine.legal_commands(state)
        for lc in frame.commands:
            try:
                after, _ = self.engine.apply(state, lc.command, own)
            except IllegalCommand:
                kept.append(lc)
                continue
            if position_key(after, self.engine.types, self.player) in self._seen:
                held.append(lc.id)
            else:
                kept.append(lc)
        if not kept:
            return list(frame.commands), []
        return kept, held

    def select(self, state: State, frame: DecisionFrame) -> str:
        """One decision. It always gives an identity from the frame (FR-47)."""
        if not frame.commands:
            raise ValueError("no legal command")
        self.counters.decisions += 1
        commands, held = self.offered(state, frame)
        if held:
            self.counters.refused += 1
            self.counters.refused_commands += len(held)
        legal_ids = [lc.id for lc in commands]
        if len(legal_ids) == 1:
            return legal_ids[0]
        prompt = text_state(self.engine, state, frame, self.player, self.plans[-MAX_PLANS:], commands)
        message = prompt
        started = time.perf_counter()
        for attempt in range(self.retries + 1):
            try:
                constraint = schema.json_schema(legal_ids) if self.constrained else None
                answer = self.provider.complete(
                    SYSTEM_PROMPT, message, self.max_tokens, json_schema=constraint
                )
                self.counters.calls += 1
            except ProviderUnavailable as exc:
                self.counters.timeouts += 1
                self._record(frame, None, f"provider unavailable: {exc}", attempt)
                break
            except ProviderError as exc:
                self.counters.provider_errors += 1
                self._record(frame, None, f"provider error: {exc}", attempt)
                break
            try:
                decision = schema.parse(answer.text, legal_ids)
            except schema.SchemaError as exc:
                self.counters.invalid += 1
                if attempt < self.retries:
                    self.counters.retries += 1
                    message = f"{prompt}\n\nYour last answer was refused: {exc}. Answer again."
                    continue
                self._record(frame, answer, f"invalid answer: {exc}", attempt, held=held)
                break
            self.counters.seconds.append(time.perf_counter() - started)
            if decision.plan:
                self.plans.append(decision.plan)
            self._record(frame, answer, "", attempt, decision, held=held)
            return decision.command_id
        self.counters.seconds.append(time.perf_counter() - started)
        self.counters.fallbacks += 1
        fallback = decide(self.default_agent, state, frame)
        if fallback in held:
            # The default agent stands under the guard too: its own choice of a return
            # would be the cycle again. The first offered command of its kind, else the first.
            kind = frame.by_id(fallback).command.action
            same = [lc.id for lc in commands if lc.command.action == kind]
            fallback = same[0] if same else legal_ids[0]
        return fallback

    def _record(
        self,
        frame: DecisionFrame,
        answer: Answer | None,
        problem: str,
        attempt: int,
        decision: schema.Decision | None = None,
        held: Sequence[str] = (),
    ) -> None:
        """One line of the harness log. It never holds a key or an opponent's hidden unit."""
        entry: dict[str, Any] = {
            "decision": self.counters.decisions,
            "phase": frame.phase,
            "sub_step": frame.sub_step,
            "legal": len(frame.commands),
            "attempt": attempt,
            "problem": problem,
        }
        if held:
            entry["held"] = list(held)
        if answer is not None:
            entry["answer"] = answer.to_dict()
        if decision is not None:
            entry["command_id"] = decision.command_id
            entry["reason"] = decision.reason
        self.log.append(entry)

    def report(self) -> dict[str, Any]:
        """The record of one game for the run artifact (TC-16, OR-02)."""
        return {
            "agent": self.name,
            "provider": self.provider.name,
            "model": self.provider.model,
            "player": self.player,
            "retries_allowed": self.retries,
            "constrained": self.constrained,
            **self.counters.to_dict(),
        }
