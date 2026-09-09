"""The model agent harness (FR-45 to FR-49, FR-59, SR-04, SR-09).

The harness is the fourth agent family behind the same interface as the others: it gets a
state and a frame, and it gives back one command identity. What it does between those two
is:

1. Build a text state from the acting player's view and from nothing else (FR-45, SR-09).
   The text has the units the player may see, the terrain of the hexes that matter, and
   the legal command list with an identity for each command.
2. Send the text to a provider and let the model write its analysis in free text first,
   then one JSON object that a flat schema constrains (FR-46).
3. When the object does not satisfy the schema, or its command identity is not in the
   list, send the rejection message back and ask again, up to a count (FR-47).
4. After the last failure, take the command that the scripted agent would take, and record
   the fallback (FR-47).

Three things the harness never does. It never sends an image (FR-48). It never runs the
model output: the output is a command identity that the harness looks up in the frame the
core gave (SR-04). It never puts a key in a log line or an artifact (SR-01).

The harness records the four rates that TC-16 asks for: invalid commands, retries,
fallbacks, and timeouts. FR-59 says that a model with a median decision time above five
seconds is an asynchronous opponent, so the harness records each decision time and says
which side of that line it is on.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from slagents.prompted import schema
from slagents.prompted.providers import Answer, Provider, ProviderError, ProviderUnavailable
from slcore import geometry
from slcore.engine import Engine
from slcore.frame import DecisionFrame
from slcore.game import State
from slcore.los_eval import evaluate as evaluate_los
from slcore.view import build as build_view

ASYNCHRONOUS_SECONDS = 5.0
DEFAULT_RETRIES = 2
MAX_COMMANDS_IN_PROMPT = 60
MAX_PLANS = 3
NEAREST_ENEMIES = 4

SYSTEM_PROMPT = (
    "You command one side in a tactical infantry game on a hex board. You get the state "
    "that your side can see and the list of legal commands. You select one command from "
    "that list. You never invent a command, and you never name a hex that is not in the "
    "list. Write a short analysis first, then one JSON object."
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
            "median_seconds": round(median, 3),
            "max_seconds": round(max(self.seconds), 3) if self.seconds else 0.0,
            "asynchronous": median > ASYNCHRONOUS_SECONDS,
        }


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
        from slcore.view import concealed_from

        if concealed_from(state, other, viewer):
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


def text_state(engine: Engine, state: State, frame: DecisionFrame, viewer: int, plans: Sequence[str]) -> str:
    """The compact text of FR-45, from the acting player's view alone (SR-09)."""
    document = build_view(state, engine.types, viewer)
    side = engine.scenario.players()[viewer]
    lines = [
        f"Scenario {engine.scenario.id}. You are the {side} side, player {viewer}.",
        f"Turn {document['turn']} of {document['turn_limit']}. Phase {document['phase']}, step {frame.sub_step}.",
        "",
        "Your units:",
    ]
    own = [u for u in document["units"] if u["own"] and u["hex"] is not None]
    for unit in sorted(own, key=lambda u: u["id"]):
        marks = [name for name in ("broken", "moved", "prep_fired", "dm", "berserk", "malfunction") if unit[name]]
        state_text = f" [{', '.join(marks)}]" if marks else ""
        where = unit["hex"]
        terrain = engine.board.hex(geometry.parse_hex_id(where)).terrain
        lines.append(
            f"  {unit['id']}: {unit['type']}{' ' + unit['name'] if unit['name'] else ''} in {where} ({terrain}), "
            f"morale {unit['morale']}{state_text}"
        )
    lines.append("")
    lines.append("Enemy units you can see:")
    other = [u for u in document["units"] if not u["own"] and u["hex"] is not None]
    if not other:
        lines.append("  none")
    for unit in sorted(other, key=lambda u: u["id"]):
        lines.append(f"  {unit['id']}: {unit['type']} in {unit['hex']}")
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
    lines.append("Legal commands. Answer with one of these identities:")
    for legal in frame.commands[:MAX_COMMANDS_IN_PROMPT]:
        lines.append(f"  {legal.id} {command_text(engine, legal.payload)}")
    if len(frame.commands) > MAX_COMMANDS_IN_PROMPT:
        lines.append(f"  ... and {len(frame.commands) - MAX_COMMANDS_IN_PROMPT} more of the same kinds")
    lines.append("")
    lines.append(schema.describe([lc.id for lc in frame.commands]))
    return "\n".join(lines)


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

    def select(self, state: State, frame: DecisionFrame) -> str:
        """One decision. It always gives an identity from the frame (FR-47)."""
        if not frame.commands:
            raise ValueError("no legal command")
        self.counters.decisions += 1
        legal_ids = [lc.id for lc in frame.commands]
        if len(legal_ids) == 1:
            return legal_ids[0]
        prompt = text_state(self.engine, state, frame, self.player, self.plans[-MAX_PLANS:])
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
                self._record(frame, answer, f"invalid answer: {exc}", attempt)
                break
            self.counters.seconds.append(time.perf_counter() - started)
            if decision.plan:
                self.plans.append(decision.plan)
            self._record(frame, answer, "", attempt, decision)
            return decision.command_id
        self.counters.seconds.append(time.perf_counter() - started)
        self.counters.fallbacks += 1
        return self.default_agent.select(state, frame)

    def _record(
        self,
        frame: DecisionFrame,
        answer: Answer | None,
        problem: str,
        attempt: int,
        decision: schema.Decision | None = None,
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
