"""The tactical overlay of the two windows: one model, two drawings.

The 2D window (`slwindow.marks`) and the 3D window (`slwindow3d.indicators`) draw the same
model. This module builds it and holds no game library, so a test reads the model with no
screen. It reads what the host sends and nothing else: the view, the legal list, the log
tail, and the answers to `los_request`. It applies no rule and it holds no rule table
(AR-06). The line of sight in the model is the host's answer, never a calculation here.

The model has five parts:

- The focus unit. A person's click pins it. With no pin it is the unit that acted last,
  so a watcher of two computer opponents sees the options of the unit that plays. The
  options of the focus unit are its move destinations, its fire targets, and its track.
- The shades. Each is one hex and one tone. A tone is a key, and each window maps the key
  to its own colour. The tones are quiet: a shade is a translucent fill on the ground.
- The tracers. A fire is a thin line from the firer to the target in the tone of its
  phase, and it lingers for a short time. A watcher reads a prep fire, a defensive fire,
  and an advancing fire apart by the tone.
- The bursts. The result of a fire is a small mark on the target hex in the tone of the
  result: no effect, a morale check, a break, or a kill.
- The ghosts. Rule 16.1 puts a moved unit back on a hex of its track for the defensive
  fire, and rule 16.3 sends it back. The counter stays at its end hex and a ghost stands
  where the fire catches it, so no counter warps on the board.

A time is a number of seconds that the caller passes in. The model keeps no clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

# ------------------------------------------------------------------------- the tones

TONE_FOCUS = "focus"
TONE_MOVE = "move"
TONE_TARGET = "target"
TONE_TRACK = "track"
TONE_LOS = "los"
TONE_LOS_BLOCKED = "los_blocked"
TONE_RETURN = "return"
TONE_MELEE = "melee"

# When two tones fall on one hex, the higher rank wins.
TONE_RANK = {
    TONE_TRACK: 1,
    TONE_MOVE: 2,
    TONE_LOS: 3,
    TONE_TARGET: 4,
    TONE_MELEE: 5,
    TONE_RETURN: 6,
    TONE_LOS_BLOCKED: 7,
    TONE_FOCUS: 8,
}

# ------------------------------------------------------------------- the fire kinds

FIRE_PREP = "prep"
FIRE_DEFENSIVE = "defensive"
FIRE_ADVANCING = "advancing"
FIRE_OTHER = "other"

_FIRE_KIND_BY_PHASE = {
    "prep_fire": FIRE_PREP,
    "defensive_fire": FIRE_DEFENSIVE,
    "advancing_fire": FIRE_ADVANCING,
    "movement": FIRE_DEFENSIVE,
}

# --------------------------------------------------------------------- the results

RESULT_NONE = "none"
RESULT_CHECK = "check"
RESULT_BROKEN = "broken"
RESULT_KILL = "kill"

_RESULT_RANK = {RESULT_NONE: 0, RESULT_CHECK: 1, RESULT_BROKEN: 2, RESULT_KILL: 3}
_KILL_KINDS = {"eliminated", "wreck", "cc_kill", "weapon_eliminated"}
_BROKEN_KINDS = {"broken", "berserk", "immobilized", "crew_abandons"}
_CHECK_KINDS = {"morale_pass", "pre_afv_check"}

# ---------------------------------------------------------------------- the events

_FIRE_EVENTS = {"fire", "afv_fire", "to_hit"}
_MOVE_EVENTS = {"move", "advance", "stack_move", "vehicle_move", "rout"}
_CLOSE_COMBAT_EVENTS = {"cc_declare", "cc_kill", "cc_miss"}
# An event of one of these kinds ends the batch of results that follows a fire.
_BATCH_BREAK = _FIRE_EVENTS | _MOVE_EVENTS | {"phase", "player_turn_end", "turn_start", "place"}
# The event kinds that name the unit that acts, and the field that holds it.
_ACTING_FIELD = {
    "move": "unit",
    "advance": "unit",
    "vehicle_move": "unit",
    "vehicle_pivot": "unit",
    "rout": "unit",
    "place": "unit",
    "afv_fire": "unit",
    "to_hit": "unit",
    "stack_move": "leader",
    "pickup": "unit",
    "drop": "unit",
    "rally_failed": "unit",
    "rallied": "unit",
}

# -------------------------------------------------------------------- the commands

_MOVE_ACTIONS = {"move", "stack_move", "advance", "vehicle_move", "sewer_move", "rout"}
_FIRE_ACTIONS = {
    "group_add",
    "group_add_weapon",
    "group_fire",
    "ft_fire",
    "afv_fire",
    "afv_mg",
    "at_fire",
    "afv_attack",
    "cc_afv",
    "cc_attack",
    "explode_demo",
}

# ---------------------------------------------------------------------- the linger

LINGER_TRACER = 2.0
LINGER_BURST = 2.8
LINGER_TRACK = 3.2
LINGER_LOS = 2.0


@dataclass(frozen=True)
class Tracer:
    source: str
    target: str
    kind: str
    result: str
    phase: str
    until: float


@dataclass(frozen=True)
class Burst:
    hex: str
    result: str
    until: float


@dataclass(frozen=True)
class Ghost:
    unit: int
    hex: str
    end: str


@dataclass
class Overlay:
    """What the two windows draw over the board for one frame."""

    focus: int | None = None
    focus_hex: str | None = None
    shades: dict[str, str] = field(default_factory=dict)
    tracers: list[Tracer] = field(default_factory=list)
    bursts: list[Burst] = field(default_factory=list)
    ghosts: list[Ghost] = field(default_factory=list)
    # The pairs of hexes the window has no line of sight answer for yet. The window sends
    # one `los_request` for each and the host answers (FR-34, TC-40).
    los_wanted: list[tuple[str, str]] = field(default_factory=list)

    def key(self) -> tuple:
        """A value that changes when the drawing has to change, so a window that keeps
        its nodes between frames rebuilds them only then."""
        return (
            self.focus,
            self.focus_hex,
            tuple(sorted(self.shades.items())),
            tuple(self.tracers),
            tuple(self.bursts),
            tuple(self.ghosts),
        )


@dataclass(frozen=True)
class _Shade:
    hex: str
    tone: str
    until: float


def position_of(unit: dict[str, Any]) -> str | None:
    """The hex a window draws a unit in. Rule 16.1 moves a unit back along its track for
    the defensive fire, and the window keeps the counter at its end hex."""
    returned = unit.get("returned_from")
    if returned:
        return str(returned)
    here = unit.get("hex")
    return None if here is None else str(here)


def units_in(view: dict[str, Any] | None, hex_id: str | None) -> list[dict[str, Any]]:
    """The units a window draws in one hex, in the order of the stack: a vehicle first,
    then the infantry by id, which is how rule 29.3 stacks them on a table."""
    if hex_id is None or not isinstance(view, dict):
        return []
    found = [u for u in view.get("units", []) if position_of(u) == hex_id and u.get("carrier") is None]
    found.sort(key=lambda u: (u.get("kind") != "vehicle", int(u["id"])))
    return found


def next_focus(view: dict[str, Any] | None, hex_id: str | None, pinned: int | None) -> int | None:
    """The unit a click puts in focus: the top of the stack, or the next one down when the
    same stack is clicked again. A click on an empty hex clears the pin."""
    ids = [int(u["id"]) for u in units_in(view, hex_id)]
    if not ids:
        return None
    if pinned in ids:
        return ids[(ids.index(pinned) + 1) % len(ids)]
    return ids[0]


def payload_of(command: dict[str, Any]) -> dict[str, Any]:
    """The payload of a legal command. The host sends `{"id", "payload"}`, and a
    constructed command in a test is the payload itself."""
    payload = command.get("payload")
    return payload if isinstance(payload, dict) else command


def fire_kind(phase: Any) -> str:
    return _FIRE_KIND_BY_PHASE.get(str(phase or ""), FIRE_OTHER)


def result_of(kinds: Iterable[str], fire_results: Iterable[Any] = ()) -> str:
    """The strongest result among the events that followed a fire."""
    best = RESULT_NONE
    for kind in kinds:
        if kind in _KILL_KINDS:
            found = RESULT_KILL
        elif kind in _BROKEN_KINDS:
            found = RESULT_BROKEN
        elif kind in _CHECK_KINDS:
            found = RESULT_CHECK
        else:
            continue
        if _RESULT_RANK[found] > _RESULT_RANK[best]:
            best = found
    for value in fire_results:
        # The IFT gives "-" for no effect, "M" for a morale check, a number for a check
        # with a modifier, and "KIA" (`slcore.tabledata`).
        text = str(value)
        if text == "KIA":
            found = RESULT_KILL
        elif text in ("-", "NONE", "None", ""):
            found = RESULT_NONE
        else:
            found = RESULT_CHECK
        if _RESULT_RANK[found] > _RESULT_RANK[best]:
            best = found
    return best


class Tracker:
    """The overlay across frames: the events it has read, the marks that linger, and the
    unit that acted last. One tracker for one window."""

    def __init__(self) -> None:
        self.seen_seq = -1
        self.primed = False
        self.acting: int | None = None
        self._tracers: list[Tracer] = []
        self._bursts: list[Burst] = []
        self._shades: list[_Shade] = []
        self._fire_los: list[tuple[str, str, float]] = []

    def reset(self) -> None:
        """A new board is a new game, so the marks of the last one go."""
        self.seen_seq = -1
        self.primed = False
        self.acting = None
        self._tracers = []
        self._bursts = []
        self._shades = []
        self._fire_los = []

    # ------------------------------------------------------------------ the update

    def update(
        self,
        snapshot: Any,
        now: float,
        pinned: int | None = None,
        pointer_hex: str | None = None,
        los: dict[tuple[str, str], dict[str, Any]] | None = None,
    ) -> Overlay:
        """The model for one frame.

        `pinned` is the unit a person clicked, or None. `pointer_hex` is the hex under the
        pointer, for a line of sight from the focus unit. `los` is the table of answers
        the window has, by pair of hex ids.
        """
        overlay = Overlay()
        if snapshot is None:
            return overlay
        view = getattr(snapshot, "view", None)
        if not isinstance(view, dict):
            return overlay
        units = {int(u["id"]): u for u in view.get("units", []) if "id" in u}
        legal = list(getattr(snapshot, "legal", None) or [])
        log = list(getattr(snapshot, "log", None) or [])
        los = los or {}

        self._read_log(log, units, now)
        self._expire(now)

        focus = self._focus(pinned, units, view)
        overlay.focus = focus
        overlay.focus_hex = position_of(units[focus]) if focus is not None else None

        shades: list[tuple[str, str]] = [(s.hex, s.tone) for s in self._shades]
        for hex_id in view.get("melee", []) or []:
            shades.append((str(hex_id), TONE_MELEE))
        if focus is not None:
            shades.extend(self._focus_shades(units[focus], legal, view))
            if overlay.focus_hex and pointer_hex and pointer_hex != overlay.focus_hex:
                pair = (overlay.focus_hex, str(pointer_hex))
                answer = los.get(pair)
                if answer is None:
                    overlay.los_wanted.append(pair)
                else:
                    shades.extend(_los_shades(answer))
        for source, target, _until in self._fire_los:
            answer = los.get((source, target))
            if answer is None:
                overlay.los_wanted.append((source, target))
            else:
                shades.extend(_los_shades(answer))
        for unit in units.values():
            returned = unit.get("returned_from")
            here = unit.get("hex")
            if returned and here and unit.get("carrier") is None:
                overlay.ghosts.append(Ghost(int(unit["id"]), str(here), str(returned)))
                shades.append((str(here), TONE_RETURN))
        if overlay.focus_hex:
            shades.append((overlay.focus_hex, TONE_FOCUS))

        overlay.shades = _merge(shades)
        overlay.tracers = list(self._tracers)
        overlay.bursts = list(self._bursts)
        overlay.los_wanted = sorted(set(overlay.los_wanted))
        return overlay

    # ------------------------------------------------------------------- the focus

    def _focus(self, pinned: int | None, units: dict[int, dict[str, Any]], view: dict[str, Any]) -> int | None:
        if pinned is not None and pinned in units and position_of(units[pinned]) is not None:
            return pinned
        if self.acting is not None and self.acting in units and position_of(units[self.acting]) is not None:
            return self.acting
        group = view.get("fire_group")
        if isinstance(group, dict):
            for member in group.get("members", []) or []:
                unit_id = int(member[0]) if isinstance(member, (list, tuple)) else int(member)
                if unit_id in units and position_of(units[unit_id]) is not None:
                    return unit_id
        return None

    @staticmethod
    def _focus_shades(unit: dict[str, Any], legal: list[dict[str, Any]], view: dict[str, Any]) -> list[tuple[str, str]]:
        """The options of the focus unit: where it can go, what it can fire at, its track."""
        out: list[tuple[str, str]] = []
        unit_id = int(unit["id"])
        for hex_id in unit.get("track", []) or []:
            out.append((str(hex_id), TONE_TRACK))
        for command in legal:
            payload = payload_of(command)
            action = str(payload.get("action", ""))
            target = payload.get("hex")
            if target is None or unit_id not in {int(u) for u in payload.get("units", [])}:
                continue
            if action in _MOVE_ACTIONS:
                out.append((str(target), TONE_MOVE))
            elif action in _FIRE_ACTIONS:
                out.append((str(target), TONE_TARGET))
        group = view.get("fire_group")
        if isinstance(group, dict) and group.get("target"):
            members = {int(m[0]) if isinstance(m, (list, tuple)) else int(m) for m in group.get("members", []) or []}
            if unit_id in members:
                out.append((str(group["target"]), TONE_TARGET))
        return out

    # --------------------------------------------------------------------- the log

    def _read_log(self, log: list[dict[str, Any]], units: dict[int, dict[str, Any]], now: float) -> None:
        """Turn the events that are new since the last frame into marks that linger.

        The host gives each entry a `seq`, so a re-sent tail is not read twice. The first
        read seeds the mark and draws nothing, so a watcher who joins a running game does
        not see its past as one burst.
        """
        fresh: list[dict[str, Any]] = []
        for index, entry in enumerate(log):
            seq = int(entry.get("seq", index))
            if seq > self.seen_seq:
                fresh.append(entry)
                self.seen_seq = seq
        if not self.primed:
            self.primed = True
            return
        i = 0
        while i < len(fresh):
            entry = fresh[i]
            kind = str(entry.get("kind", ""))
            data = entry.get("data") or {}
            field_name = _ACTING_FIELD.get(kind)
            if field_name and data.get(field_name) is not None:
                self.acting = int(data[field_name])
            if kind in _FIRE_EVENTS:
                j = i + 1
                following: list[str] = []
                results: list[Any] = []
                while j < len(fresh) and str(fresh[j].get("kind", "")) not in _BATCH_BREAK:
                    following.append(str(fresh[j].get("kind", "")))
                    if fresh[j].get("kind") == "fire_result":
                        results.append((fresh[j].get("data") or {}).get("result"))
                    j += 1
                self._add_fire(kind, data, units, result_of(following, results), now)
                i = j
                continue
            if kind in _MOVE_EVENTS:
                self._add_move(data, now)
            elif kind in _CLOSE_COMBAT_EVENTS:
                self._add_close_combat(kind, data, units, now)
            i += 1

    def _add_fire(self, kind: str, data: dict[str, Any], units: dict[int, dict[str, Any]], result: str, now: float) -> None:
        target = data.get("target")
        if target is None:
            return
        target = str(target)
        firers: list[int] = []
        if kind == "fire":
            for member in data.get("members", []) or []:
                if isinstance(member, dict) and member.get("unit") is not None:
                    firers.append(int(member["unit"]))
        elif data.get("unit") is not None:
            firers.append(int(data["unit"]))
        if firers:
            self.acting = firers[0]
        phase = str(data.get("phase", ""))
        for firer in firers:
            unit = units.get(firer)
            source = position_of(unit) if unit else None
            if source is None or source == target:
                continue
            self._tracers.append(Tracer(source, target, fire_kind(phase), result, phase, now + LINGER_TRACER))
            self._fire_los.append((source, target, now + LINGER_LOS))
        self._bursts.append(Burst(target, result, now + LINGER_BURST))

    def _add_move(self, data: dict[str, Any], now: float) -> None:
        for key in ("from", "to"):
            hex_id = data.get(key)
            if hex_id is not None:
                self._shades.append(_Shade(str(hex_id), TONE_TRACK, now + LINGER_TRACK))

    def _add_close_combat(self, kind: str, data: dict[str, Any], units: dict[int, dict[str, Any]], now: float) -> None:
        attackers = data.get("attackers") or []
        if attackers:
            self.acting = int(attackers[0])
        if kind == "cc_declare":
            return
        victim = data.get("target")
        unit = units.get(int(victim)) if victim is not None else None
        here = position_of(unit) if unit else None
        if here is None:
            attacker = data.get("attacker")
            unit = units.get(int(attacker)) if attacker is not None else None
            here = position_of(unit) if unit else None
        if here is not None:
            self._bursts.append(Burst(here, RESULT_KILL if kind == "cc_kill" else RESULT_NONE, now + LINGER_BURST))

    # ------------------------------------------------------------------ the linger

    def _expire(self, now: float) -> None:
        self._tracers = [t for t in self._tracers if t.until > now]
        self._bursts = [b for b in self._bursts if b.until > now]
        self._shades = [s for s in self._shades if s.until > now]
        self._fire_los = [f for f in self._fire_los if f[2] > now]


def _los_shades(answer: dict[str, Any]) -> list[tuple[str, str]]:
    """The hexes of one line of sight answer of the host. A clear line shades each hex it
    threads. A blocked line shades the hexes up to the block, and the block darker."""
    out: list[tuple[str, str]] = []
    traced = [str(h) for h in answer.get("traced", []) or []]
    block = answer.get("blocking_hex")
    for hex_id in traced:
        if block is not None and hex_id == str(block):
            out.append((hex_id, TONE_LOS_BLOCKED))
            break
        out.append((hex_id, TONE_LOS))
    if block is not None and str(block) not in traced:
        out.append((str(block), TONE_LOS_BLOCKED))
    return out


def _merge(shades: list[tuple[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for hex_id, tone in shades:
        held = out.get(hex_id)
        if held is None or TONE_RANK[tone] > TONE_RANK[held]:
            out[hex_id] = tone
    return out
