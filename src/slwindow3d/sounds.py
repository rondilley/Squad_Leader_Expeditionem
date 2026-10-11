"""The sounds of the game, made by code: weapons fire, explosions, footsteps, and engines.

Each sound is synthesized here from noise, decaying envelopes, filters, and low tones, so the
project ships no recorded audio and each sound is the project's own work (SR-07). The window
gets each sound as WAV bytes (`bank`) and plays it from memory (`audio.py`).

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
  weapon. A vehicle is a throbbing motor, the rhythmic clank of its tracks, and the roll of
  its road wheels, quieter than a gun.

The random parts come from a generator seeded by the sound name and the variant, so each run
makes the same sounds, and the variants of one name differ so a burst does not repeat
exactly. This module imports no part of Panda3D.
"""

from __future__ import annotations

import io
import math
import random
import wave
from array import array

RATE = 22050
VARIANTS = 3
# The footsteps are made at a lower level than the weapons, and their cues play quieter too.
STEPS_GAIN = 0.5
STEPS_VOLUME = 0.3
# A vehicle is quieter than a gun too (owner, 2026-10-10), in its file and in its cue.
ENGINE_GAIN = 0.55
ENGINE_VOLUME = 0.45

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
NAMES = (
    RIFLE, SMG, MG_FAST, MG_SLOW, FLAME, ROCKET, TANK_GUN, EXPLOSION, GRENADES, SMOKE,
    STEPS_ONE, STEPS_SQUAD, STEPS_RUN, ENGINE,
)


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


def _engine(rng: random.Random) -> _Track:
    """A tracked vehicle on the move (owner, 2026-10-10: "sound more like a motor and
    wheels/tracks driving vs. just a rumble", then "much lower frequency, they currently
    sound like someone playing a rainfall stick").

    All of it is low: nothing rings above a few hundred hertz.

    - The motor: a train of firing pulses at the firing rate of the engine, each a deep
      thump (a 38 to 46 Hz fundamental and two harmonics), a little different from cycle to
      cycle, so it throbs like a motor and does not hum; the rate climbs as it pulls away.
    - The tracks: a dull, heavy clunk of the links on the sprocket at about ten a second,
      each a short low tone with a thud of dark noise.
    - The road wheels: a low roll under it all.
    """
    seconds = 2.2
    track = _Track(seconds, rng)
    n = len(track.data)
    # The motor.
    rate = rng.uniform(22.0, 27.0)
    base = rng.uniform(38.0, 46.0)
    t = 0.0
    while t < seconds - 0.05:
        speed = 0.75 + 0.25 * min(1.0, t / 0.5)
        amp = rng.uniform(0.6, 1.0) * min(1.0, 0.3 + t / 0.25) * min(1.0, (seconds - t) / 0.4)
        start = int(t * RATE)
        for i in range(int(0.045 * RATE)):
            j = start + i
            if j >= n:
                break
            u = i / RATE
            pulse = math.exp(-u / 0.014)
            track.data[j] += amp * pulse * (
                0.7 * math.sin(2 * math.pi * base * u) + 0.35 * math.sin(2 * math.pi * 2 * base * u) + 0.12 * math.sin(2 * math.pi * 3 * base * u)
            )
        t += 1.0 / (rate * speed) * rng.uniform(0.94, 1.06)
    # The road wheels.
    track.noise(0.0, seconds, 0.18, 4.0, smooth=0.015)
    # The tracks.
    clank = rng.uniform(9.0, 12.0)
    for k in range(int(seconds * clank)):
        at = k / clank + rng.uniform(-0.006, 0.006)
        level = 0.4 * min(1.0, (seconds - at) / 0.4)
        track.tone(at, 0.07, rng.uniform(110.0, 170.0), level, 0.016, drop=0.2)
        track.noise(at, 0.05, level * 0.8, 0.012, smooth=0.05)
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
