"""The sounds of the game: weapons fire, explosions, footsteps, and engines.

Each sound but the vehicle is synthesized here from noise, decaying envelopes, filters, and
low tones, and is the project's own work (SR-07). The vehicle is a part of the owner's
recording of a tank (`assets/tank_drive.wav`, docs/ASSET_PROVENANCE.md). The window gets
each sound as WAV bytes (`bank`) and plays it from memory (`audio.py`).

- A rifle shot is a sharp crack, a short body, and a long low echo; a squad's rifle fire is
  a ragged volley of a few shots.
- A submachine gun is a fast run of lighter cracks.
- A machine gun is a burst at its rate of fire: the German MG34 and MG42 fire fast (about 20
  rounds a second, the tearing sound), the Russian and American guns slower (about 9).
- A flamethrower is a roaring whoosh with crackle; a rocket is a launch hiss and a blast; a
  tank gun is a crack and a deep boom with a long rumble; a demolition charge is the largest
  blast; grenades are a few dull bangs; smoke is a pop and a hiss.
- One man moving is a few muffled footsteps; a squad is several men stepping out of time,
  with a soft rattle of equipment; a rout is the same, faster. They are quieter than any
  weapon. A vehicle is a part of the tank recording, quieter than a gun.
- A vehicle that breaks down is a hard metal clank, a grinding scrape, and an engine that
  coughs and dies. A vehicle crew that works on a broken gun is the taps of a hammer and
  the clicks of a wrench on metal.

The random parts (and the part of the recording) come from a generator seeded by the sound
name and the variant, so each run makes the same sounds, and the variants of one name differ
so a burst does not repeat exactly. This module imports no part of Panda3D.
"""

from __future__ import annotations

import io
import math
import random
import wave
from array import array
from pathlib import Path

RATE = 22050
VARIANTS = 3
# The footsteps are made at a lower level than the weapons, and their cues play quieter too.
STEPS_GAIN = 0.5
STEPS_VOLUME = 0.3
# A vehicle is quieter than a gun too (owner, 2026-10-10), in its file and in its cue.
ENGINE_GAIN = 0.55
ENGINE_VOLUME = 0.45
# The one recorded sound: the owner's tank (docs/ASSET_PROVENANCE.md).
TANK_RECORDING = Path(__file__).resolve().parent / "assets" / "tank_drive.wav"
# The cutoff of the low-pass filter on the recording, in hertz (owner, 2026-10-11: "too
# high"). A lower cutoff takes out the clank of the tracks too, and leaves only a rumble.
ENGINE_CUTOFF = 600.0

# The sound names. `sound_cues` gives names from this list.
RIFLE = "rifle"
SMG = "smg"
MG_FAST = "mg_fast"
MG_SLOW = "mg_slow"
FLAME = "flame"
ROCKET = "rocket"
TANK_GUN = "tank_gun"
EXPLOSION = "explosion"
GRENADES = "grenades"
SMOKE = "smoke"
STEPS_ONE = "steps_one"
STEPS_SQUAD = "steps_squad"
STEPS_RUN = "steps_run"
ENGINE = "engine"
BREAKDOWN = "breakdown"
REPAIR = "repair"
NAMES = (
    RIFLE, SMG, MG_FAST, MG_SLOW, FLAME, ROCKET, TANK_GUN, EXPLOSION, GRENADES, SMOKE,
    STEPS_ONE, STEPS_SQUAD, STEPS_RUN, ENGINE, BREAKDOWN, REPAIR,
)
# A breakdown and a repair are near the level of the engine, below the guns.
BREAKDOWN_VOLUME = 0.6
REPAIR_VOLUME = 0.5


class _Track:
    """A mono buffer of float samples, with the few tools a sound needs."""

    def __init__(self, seconds: float, rng: random.Random) -> None:
        self.data = [0.0] * int(seconds * RATE)
        self.rng = rng
        # The peak level of the WAV file; a quiet sound is made quiet in the file too.
        self.gain = 0.9

    def noise(self, at: float, seconds: float, amp: float, tau: float, smooth: float = 1.0, attack: float = 0.0) -> None:
        """Noise from `at`, `amp` loud, decaying with time constant `tau`. `smooth` is the
        weight of a one-pole low-pass filter (1.0 is no filter; smaller is darker)."""
        start = int(at * RATE)
        state = 0.0
        for i in range(int(seconds * RATE)):
            j = start + i
            if j >= len(self.data):
                break
            t = i / RATE
            envelope = math.exp(-t / tau)
            if attack > 0.0 and t < attack:
                envelope *= t / attack
            state += smooth * (self.rng.uniform(-1.0, 1.0) - state)
            self.data[j] += amp * envelope * state

    def tone(self, at: float, seconds: float, freq: float, amp: float, tau: float, drop: float = 0.0) -> None:
        """A low sine tone that falls in pitch by `drop` (a share of `freq`) and decays."""
        start = int(at * RATE)
        phase = 0.0
        for i in range(int(seconds * RATE)):
            j = start + i
            if j >= len(self.data):
                break
            t = i / RATE
            f = freq * (1.0 - drop * min(1.0, t / max(seconds, 1e-6)))
            phase += 2.0 * math.pi * f / RATE
            self.data[j] += amp * math.exp(-t / tau) * math.sin(phase)

    def wav(self) -> bytes:
        peak = max(1e-6, max(abs(x) for x in self.data))
        scale = self.gain / peak
        fade = int(0.01 * RATE)
        samples = array("h")
        for i, x in enumerate(self.data):
            if i >= len(self.data) - fade:
                x *= (len(self.data) - i) / fade
            samples.append(int(max(-1.0, min(1.0, x * scale)) * 32767))
        out = io.BytesIO()
        with wave.open(out, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(samples.tobytes())
        return out.getvalue()


def _shot(track: _Track, at: float, amp: float, crack: float = 0.006, body: float = 0.05, echo: float = 0.22) -> None:
    track.noise(at, 0.04, amp, crack)
    track.noise(at, 0.3, amp * 0.6, body, smooth=0.18)
    track.noise(at + 0.01, 0.9, amp * 0.18, echo, smooth=0.05)


def _boom(track: _Track, at: float, amp: float, tau: float, freq: float) -> None:
    track.noise(at, 0.05, amp * 0.8, 0.008)
    track.noise(at, tau * 5, amp, tau, smooth=0.03)
    track.tone(at, tau * 4, freq, amp * 0.8, tau, drop=0.5)


def _step(track: _Track, at: float, amp: float) -> None:
    """One muffled footstep: a dull low thud with a soft scuff, no sharp crunch (owner,
    2026-10-10: troop movement quieter than gunfire and more muffled)."""
    track.noise(at, 0.12, amp, 0.026, smooth=0.035)
    track.noise(at + 0.006, 0.07, amp * 0.15, 0.012, smooth=0.1)


def recording() -> list[float]:
    """The samples of the owner's tank recording (2026-10-11), from -1 to 1, at `RATE`.

    `tools/make_tank_sound.py` made the file from `background/Tank_Noise.m4a`.
    """
    with wave.open(str(TANK_RECORDING), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != RATE:
            raise ValueError(f"{TANK_RECORDING} is not 16-bit mono at {RATE} Hz")
        frames = array("h", w.readframes(w.getnframes()))
    return [x / 32768.0 for x in frames]


def _lowpass(data: list[float], cutoff: float) -> list[float]:
    """A second-order low-pass filter (12 dB an octave above `cutoff`, Q of 0.707)."""
    w = 2.0 * math.pi * cutoff / RATE
    alpha = math.sin(w) / (2.0 * 0.707)
    c = math.cos(w)
    a0 = 1.0 + alpha
    b0 = b2 = (1.0 - c) / 2.0 / a0
    b1 = (1.0 - c) / a0
    a1 = -2.0 * c / a0
    a2 = (1.0 - alpha) / a0
    out = []
    x1 = x2 = y1 = y2 = 0.0
    for x in data:
        y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, x, y1, y
        out.append(y)
    return out


def _metal(track: _Track, at: float, amp: float, freq: float, tau: float) -> None:
    """One strike on steel: a short tick and three partials that are not in tune with each
    other (2.76 and 5.40 times the first, as on a plate), each one decaying."""
    track.noise(at, 0.01, amp * 0.6, 0.002, smooth=0.6)
    for ratio, level in ((1.0, 1.0), (2.76, 0.5), (5.40, 0.25)):
        track.tone(at, tau * 5, freq * ratio, amp * level, tau / ratio ** 0.5)


def _breakdown(rng: random.Random) -> _Track:
    """A vehicle breaks down (owner, 2026-10-11: "there needs to be a sound fx for it
    breaking").

    - A hard clank of heavy metal, low and ringing, as a part fails.
    - A grinding scrape of dark noise, shaken about thirty times a second.
    - The engine coughs a few times, slower each time, and stops.
    """
    track = _Track(2.6, rng)
    _metal(track, 0.0, 1.0, rng.uniform(150.0, 190.0), 0.12)
    _metal(track, 0.04, 0.5, rng.uniform(320.0, 380.0), 0.06)
    # The grinding.
    start = int(0.05 * RATE)
    state = 0.0
    shake = rng.uniform(26.0, 34.0)
    for i in range(int(0.7 * RATE)):
        t = i / RATE
        state += 0.25 * (rng.uniform(-1.0, 1.0) - state)
        envelope = math.exp(-t / 0.35) * (0.6 + 0.4 * math.sin(2 * math.pi * shake * t))
        track.data[start + i] += 0.5 * envelope * state
    # The engine coughs and dies.
    at = 0.8
    gap = 0.14
    for k in range(rng.randint(4, 6)):
        level = 0.55 * (0.75 ** k)
        track.tone(at, 0.12, rng.uniform(40.0, 48.0), level, 0.04)
        track.noise(at, 0.08, level * 0.5, 0.025, smooth=0.05)
        at += gap
        gap *= rng.uniform(1.25, 1.45)
        if at > 2.3:
            break
    track.gain = 0.8
    return track


def _repair(rng: random.Random) -> _Track:
    """A crew works on a broken gun (owner, 2026-10-11: "sound fx of the fixing please"):
    the taps of a hammer on steel at an uneven pace, and the clicks of a wrench between them.
    """
    track = _Track(2.4, rng)
    at = rng.uniform(0.0, 0.08)
    # A group of two or three taps, then a run of the wrench, and again.
    while at < 2.0:
        for _ in range(rng.randint(2, 3)):
            if at >= 2.0:
                break
            _metal(track, at, rng.uniform(0.6, 0.9), rng.uniform(820.0, 980.0), 0.05)
            at += rng.uniform(0.22, 0.32)
        for k in range(rng.randint(3, 5)):
            track.noise(at + k * 0.075, 0.012, rng.uniform(0.25, 0.4), 0.003, smooth=0.7)
        at += rng.uniform(0.4, 0.5)
    track.gain = 0.7
    return track


def _engine(rng: random.Random) -> _Track:
    """A tracked vehicle on the move: a part of the owner's recording of a tank (owner,
    2026-10-11: "I have added a sound sample of a tank driving, use it please").

    Each variant starts at another place in the recording, so the moves of one tank do not
    repeat the same part. A low-pass filter at `ENGINE_CUTOFF` takes the high part out
    (owner, 2026-10-11: "the tank sound is too high, add a low-pass filter") and keeps the
    clank of the tracks. The part fades in and out, so it starts and stops softly.
    """
    seconds = 2.2
    track = _Track(seconds, rng)
    n = len(track.data)
    source = recording()
    start = rng.randrange(0, len(source) - n)
    # The filter starts a little early, so it has settled when the part begins.
    lead = min(start, int(0.05 * RATE))
    part = _lowpass(source[start - lead:start + n], ENGINE_CUTOFF)[lead:]
    fade_in = int(0.15 * RATE)
    fade_out = int(0.4 * RATE)
    for i in range(n):
        level = min(1.0, i / fade_in, (n - i) / fade_out)
        track.data[i] = level * part[i]
    track.gain = ENGINE_GAIN
    return track


def _make(name: str, rng: random.Random) -> _Track:
    if name == RIFLE:
        track = _Track(1.4, rng)
        for _ in range(rng.randint(3, 5)):
            _shot(track, rng.uniform(0.0, 0.45), rng.uniform(0.6, 1.0))
        return track
    if name == SMG:
        track = _Track(1.3, rng)
        for k in range(8):
            _shot(track, k * 0.068 + rng.uniform(0.0, 0.006), rng.uniform(0.6, 0.85), crack=0.004, body=0.03, echo=0.15)
        return track
    if name in (MG_FAST, MG_SLOW):
        rate, rounds = (20.0, 16) if name == MG_FAST else (9.5, 8)
        track = _Track(rounds / rate + 0.9, rng)
        for k in range(rounds):
            _shot(track, k / rate + rng.uniform(0.0, 0.004), rng.uniform(0.75, 1.0), crack=0.005, body=0.04, echo=0.2)
        return track
    if name == FLAME:
        track = _Track(1.6, rng)
        track.noise(0.0, 1.5, 1.0, 0.55, smooth=0.08, attack=0.12)
        for _ in range(14):
            track.noise(rng.uniform(0.1, 1.2), 0.03, rng.uniform(0.2, 0.45), 0.006)
        return track
    if name == ROCKET:
        track = _Track(2.0, rng)
        track.noise(0.0, 0.6, 0.5, 0.35, smooth=0.5, attack=0.08)
        _boom(track, 0.55, 1.0, 0.18, 70.0)
        return track
    if name == TANK_GUN:
        track = _Track(2.4, rng)
        _boom(track, 0.0, 1.0, 0.35, 48.0)
        return track
    if name == EXPLOSION:
        track = _Track(3.0, rng)
        _boom(track, 0.0, 1.0, 0.5, 38.0)
        for _ in range(10):
            track.noise(rng.uniform(0.2, 1.4), 0.05, rng.uniform(0.08, 0.2), 0.01, smooth=0.6)
        return track
    if name == GRENADES:
        track = _Track(2.0, rng)
        for _ in range(rng.randint(2, 4)):
            _boom(track, rng.uniform(0.0, 0.9), rng.uniform(0.5, 0.8), 0.12, 85.0)
        return track
    if name == SMOKE:
        track = _Track(1.6, rng)
        track.noise(0.0, 0.05, 0.7, 0.01, smooth=0.4)
        track.noise(0.03, 1.5, 0.35, 0.5, smooth=0.7, attack=0.15)
        return track
    if name in (STEPS_ONE, STEPS_SQUAD, STEPS_RUN):
        men, pace, steps = {STEPS_ONE: (1, 0.42, 4), STEPS_SQUAD: (4, 0.42, 4), STEPS_RUN: (4, 0.26, 6)}[name]
        track = _Track(pace * steps + 0.4, rng)
        for _ in range(men):
            offset = rng.uniform(0.0, pace)
            for k in range(steps):
                _step(track, offset + k * pace + rng.uniform(-0.03, 0.03), rng.uniform(0.5, 0.9))
            if men > 1:
                # The soft rattle of equipment, filtered so it does not click.
                for _ in range(3):
                    track.noise(rng.uniform(0.0, pace * steps), 0.03, 0.05, 0.008, smooth=0.12)
        track.gain = STEPS_GAIN
        return track
    if name == ENGINE:
        return _engine(rng)
    if name == BREAKDOWN:
        return _breakdown(rng)
    if name == REPAIR:
        return _repair(rng)
    raise ValueError(f"no sound named {name!r}")


def make_sound(name: str, variant: int = 0) -> bytes:
    """One variant of one sound, as the bytes of a 16-bit mono WAV file."""
    seed = sum(ord(c) * 131 ** i for i, c in enumerate(name)) * 7 + variant
    return _make(name, random.Random(seed)).wav()


def bank(variants: int = VARIANTS) -> dict[str, list[bytes]]:
    """Each sound in `variants` variants."""
    return {name: [make_sound(name, v) for v in range(variants)] for name in NAMES}


# ---------------------------------------------------------------------- the cues

# The single-man counters: a leader, a crew, a hero. A squad is several men.
_ONE_MAN_KINDS = {"leader", "crew", "hero"}
_STEP_EVENTS = {"move", "advance"}
# A vehicle part or gun that fails (rules 39.1, 38.1, 38.2), and the repair attempt of rule
# 38.1 and 38.2 whatever its die gives. A breakdown of rule 39.1 has no repair.
_VEHICLE_FAILURES = {"gun_malfunction", "mg_malfunction"}
_VEHICLE_REPAIRS = {"afv_repaired", "afv_repair_failed", "afv_disabled"}


def _mg_name(army: str) -> str:
    """The German MG34 and MG42 fire about twenty rounds a second; the Russian and American
    machine guns about nine."""
    return MG_FAST if str(army).lower() == "german" else MG_SLOW


def sound_cues(event: dict, units: dict) -> list[tuple[str, str | None, float]]:
    """The sounds one event makes: (name, hex, volume) for each. `units` maps a unit ID to
    the unit document of the view. Each fact comes from the event or the view (AR-06)."""
    from slwindow3d import firekinds as fk

    out: list[tuple[str, str | None, float]] = []
    by_kind = {
        fk.RIFLE: RIFLE,
        fk.SMG: SMG,
        fk.FLAME: FLAME,
        fk.ROCKET: ROCKET,
        fk.GUN: TANK_GUN,
        fk.SMOKE: SMOKE,
        fk.GRENADES: GRENADES,
        fk.OVERRUN: ENGINE,
    }
    for shot in fk.shots_for(event, units):
        where = shot.source or shot.target
        if shot.kind == fk.MG:
            out.append((_mg_name(shot.army), where, min(1.0, 0.55 + 0.15 * shot.size)))
        elif shot.kind == fk.BLAST:
            out.append((EXPLOSION if shot.size >= 2 else GRENADES, shot.target, 1.0))
        elif shot.kind == fk.OVERRUN:
            out.append((ENGINE, shot.target, ENGINE_VOLUME * 1.3))
        elif shot.kind in by_kind:
            out.append((by_kind[shot.kind], where, 0.8))
    kind = str(event.get("kind", ""))
    data = event.get("data") or {}
    if kind in _STEP_EVENTS:
        unit = units.get(data.get("unit"), {})
        if unit.get("kind") == "vehicle":
            out.append((ENGINE, data.get("to"), ENGINE_VOLUME))
        elif unit.get("kind") in _ONE_MAN_KINDS:
            out.append((STEPS_ONE, data.get("to"), STEPS_VOLUME * 0.8))
        elif unit:
            out.append((STEPS_SQUAD, data.get("to"), STEPS_VOLUME))
    elif kind == "stack_move":
        out.append((STEPS_SQUAD, data.get("to"), STEPS_VOLUME))
    elif kind == "rout":
        out.append((STEPS_RUN, data.get("to"), STEPS_VOLUME))
    elif kind == "vehicle_move":
        out.append((ENGINE, data.get("to"), ENGINE_VOLUME))
    elif kind == "vehicle_pivot":
        unit = units.get(data.get("unit"), {})
        out.append((ENGINE, unit.get("hex"), ENGINE_VOLUME * 0.6))
    elif (kind == "breakdown_roll" and data.get("immobilized")) or kind in _VEHICLE_FAILURES:
        unit = units.get(data.get("unit"), {})
        out.append((BREAKDOWN, unit.get("hex"), BREAKDOWN_VOLUME))
    elif kind in _VEHICLE_REPAIRS:
        unit = units.get(data.get("unit"), {})
        out.append((REPAIR, unit.get("hex"), REPAIR_VOLUME))
    return out


def merge_cues(cues: list[tuple[str, str | None, float]], limit: int = 4) -> list[tuple[str, str | None, float]]:
    """The cues of one frame, once each: the same sound at the same hex plays one time at
    its loudest, and at most `limit` sounds start in one frame, the loudest first."""
    best: dict[tuple[str, str | None], float] = {}
    for name, where, volume in cues:
        key = (name, where)
        best[key] = max(volume, best.get(key, 0.0))
    ordered = sorted(best.items(), key=lambda item: -item[1])[:limit]
    return [(name, where, volume) for (name, where), volume in ordered]
