"""The sound effects: the synthesized sounds, the cues of the events, and the sound board.

The sounds are made by code (`sounds.py`), so the tests read the WAV bytes. The cues come
from real games of the scripted agents. The board test runs in the offscreen window with the
null audio library of the tests, and reads what the board played.
"""

from __future__ import annotations

import io
import wave
from array import array

import pytest

from slcli.play import build_engine, make_agent
from slcore import view as core_view
from slwindow3d import sounds


def _samples(data: bytes) -> tuple[array, int]:
    with wave.open(io.BytesIO(data)) as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2
        rate = w.getframerate()
        frames = array("h", w.readframes(w.getnframes()))
    return frames, rate


@pytest.mark.parametrize("name", sounds.NAMES)
def test_each_sound_is_a_short_wav_with_sound_in_it_and_no_clip(name):
    data = sounds.make_sound(name, 0)
    frames, rate = _samples(data)
    seconds = len(frames) / rate
    assert 0.5 <= seconds <= 3.5
    peak = max(abs(x) for x in frames)
    assert 12000 <= peak <= 32767
    rms = (sum(x * x for x in frames) / len(frames)) ** 0.5
    assert rms > 300, f"{name} is close to silent"
    # The same name and variant give the same bytes; another variant differs.
    assert sounds.make_sound(name, 0) == data
    assert sounds.make_sound(name, 1) != data


def test_the_sounds_differ_from_each_other():
    made = {name: sounds.make_sound(name, 0) for name in sounds.NAMES}
    assert len(set(made.values())) == len(sounds.NAMES)


def _events(scenario, agent, seeds, limit=3000):
    engine = build_engine(scenario)
    for seed in seeds:
        state = engine.new_game(seed)
        agents = {p: make_agent(agent, engine, seed, p) for p in (0, 1)}
        count = 0
        while not state.game_over and count < limit:
            frame = engine.legal_commands(state)
            before = core_view.build(state, engine.types, core_view.SPECTATOR, spectator=True)
            state, events = engine.apply(state, frame.by_id(agents[state.active].select(state, frame)).command, frame)
            units = {u["id"]: u for u in before["units"]}
            for event in events:
                yield event.to_dict(), units
            count += 1


def test_the_cues_of_movement_and_fire_from_real_games():
    seen = set()
    for event, units in list(_events("s01_guards_counterattack", "v1", range(1))) + list(_events("s04_armor_probe", "v3", range(2))):
        cues = sounds.sound_cues(event, units)
        names = {name for name, _, _ in cues}
        seen |= names
        kind, data = event["kind"], event["data"]
        if kind in ("move", "advance"):
            unit = units[data["unit"]]
            expected = {"leader": sounds.STEPS_ONE, "squad": sounds.STEPS_SQUAD, "vehicle": sounds.ENGINE}.get(unit["kind"])
            if expected:
                assert names == {expected}, (unit["kind"], names)
            assert all(where == data["to"] for _, where, _ in cues)
        if kind == "rout":
            assert names == {sounds.STEPS_RUN}
        if kind == "vehicle_move":
            assert names == {sounds.ENGINE}
        if kind == "to_hit":
            assert names == {sounds.TANK_GUN}
        if kind == "fire":
            for member in data["members"]:
                weapon = member.get("weapon")
                if weapon is not None and units[weapon]["type"] in ("LMG", "MMG", "HMG"):
                    army = units[member["unit"]]["nationality"]
                    assert (sounds.MG_FAST if army == "german" else sounds.MG_SLOW) in names
    assert {sounds.STEPS_ONE, sounds.STEPS_SQUAD, sounds.ENGINE, sounds.MG_FAST, sounds.MG_SLOW} <= seen


def test_one_frame_plays_each_sound_once_and_not_too_many():
    cues = [("rifle", "C3", 0.5), ("rifle", "C3", 0.8), ("rifle", "D3", 0.6), ("mg_fast", "C3", 0.9)] + [
        ("steps_squad", f"E{i}", 0.3) for i in range(6)
    ]
    merged = sounds.merge_cues(cues, limit=4)
    assert len(merged) == 4
    assert ("rifle", "C3", 0.8) in merged and ("mg_fast", "C3", 0.9) in merged
    assert len({(n, w) for n, w, _ in merged}) == 4


def test_the_sound_board_plays_the_cues_of_new_events_in_the_window():
    pytest.importorskip("panda3d")
    import builtins

    from panda3d.core import loadPrcFileData

    loadPrcFileData("", "window-type offscreen")
    loadPrcFileData("", "audio-library-name null")
    from slcore.view import board_document
    from slwindow3d.app import Board3DApp
    from slwindow3d.audio import SoundBoard

    app = getattr(builtins, "base", None)
    made = False
    if not isinstance(app, Board3DApp):
        app = Board3DApp(None)
        made = True
    try:
        engine = build_engine("s01_guards_counterattack")
        app.set_board(board_document(engine.board))
        board = SoundBoard(app)
        app.sound_board = board
        app._hook_sound()
        assert app.indicators.on_new_events == board.on_events
        units = {1: {"id": 1, "kind": "squad", "type": "4-6-7", "hex": "C3", "nationality": "german", "range": 6}}
        move = {"rule_id": "5.5", "kind": "move", "data": {"unit": 1, "from": "C3", "to": "C4"}}
        board.on_events([move], units)
        assert board.played[-1][:2] == (sounds.STEPS_SQUAD, "C4")
        assert board.toggle_mute() is True
        board.on_events([move], units)
        assert board.played[-1][:2] == (sounds.STEPS_SQUAD, "C4")
        assert board.toggle_mute() is False
    finally:
        app.sound_board = None
        if app.indicators is not None:
            app.indicators.on_new_events = None
        if made:
            app.destroy()


def _brightness(frames) -> float:
    """The mean size of the change from one sample to the next, against the mean size of a
    sample: a muffled sound changes slowly, a sharp one fast."""
    change = sum(abs(frames[i] - frames[i - 1]) for i in range(1, len(frames))) / len(frames)
    level = sum(abs(x) for x in frames) / len(frames)
    return change / max(1.0, level)


def test_troop_movement_is_quieter_and_more_muffled_than_gunfire():
    """The owner: "make the troop movements quieter than the gun fire and more muffled"."""
    def loudness(name):
        frames, _ = _samples(sounds.make_sound(name, 0))
        return max(abs(x) for x in frames)

    guns = (sounds.RIFLE, sounds.SMG, sounds.MG_FAST, sounds.MG_SLOW)
    steps = (sounds.STEPS_ONE, sounds.STEPS_SQUAD, sounds.STEPS_RUN)
    quietest_gun = min(loudness(n) for n in guns)
    for name in steps:
        assert loudness(name) < 0.65 * quietest_gun
        frames, _ = _samples(sounds.make_sound(name, 0))
        rifle, _ = _samples(sounds.make_sound(sounds.RIFLE, 0))
        assert _brightness(frames) < 0.5 * _brightness(rifle), f"{name} is not muffled"
    # The cues of movement play quieter than the cues of any fire.
    move = {"rule_id": "5.5", "kind": "move", "data": {"unit": 1, "from": "C3", "to": "C4"}}
    rifle = {"rule_id": "10.6", "kind": "fire", "data": {"target": "D4", "members": [{"unit": 1, "weapon": None}]}}
    units = {1: {"id": 1, "kind": "squad", "type": "4-6-7", "hex": "C3", "nationality": "german", "range": 6}}
    step_volume = sounds.sound_cues(move, units)[0][2]
    fire_volume = sounds.sound_cues(rifle, units)[0][2]
    assert step_volume <= 0.5 * fire_volume


def _rhythm(frames, rate, low_ms: float, high_ms: float) -> float:
    """The strongest repeat of the high-frequency envelope at a lag in this range, from 0 to
    1: a track clank every 80 to 110 ms gives a strong one, a rumble gives a weak one."""
    window = int(rate * 0.005)
    high = [abs(frames[i] - frames[i - 1]) for i in range(1, len(frames))]
    env = [sum(high[k:k + window]) for k in range(0, len(high) - window, window)]
    mean = sum(env) / len(env)
    env = [e - mean for e in env]
    norm = sum(e * e for e in env) or 1.0
    best = 0.0
    for lag in range(int(low_ms / 5), int(high_ms / 5) + 1):
        best = max(best, sum(env[i] * env[i + lag] for i in range(len(env) - lag)) / norm)
    return best


def _mean_frequency(frames, rate) -> float:
    """The RMS frequency of a sound in hertz, from the energy of its slope against its
    energy: a sine of f hertz gives f."""
    import math

    energy = sum(x * x for x in frames) or 1.0
    slope = sum((frames[i] - frames[i - 1]) ** 2 for i in range(1, len(frames)))
    return rate / (2 * math.pi) * math.sqrt(slope / energy)


def test_a_vehicle_is_quieter_than_a_gun_and_sounds_like_a_motor_and_tracks():
    """The owner: "The sound of vehicles needs to be less loud than guns, and sound more like
    a motor and wheels/tracks driving vs. just a rumble"."""
    import random

    def peak(name):
        frames, _ = _samples(sounds.make_sound(name, 0))
        return max(abs(x) for x in frames)

    quietest_gun = min(peak(n) for n in (sounds.RIFLE, sounds.SMG, sounds.MG_FAST, sounds.MG_SLOW, sounds.TANK_GUN))
    for variant in range(sounds.VARIANTS):
        frames, rate = _samples(sounds.make_sound(sounds.ENGINE, variant))
        assert max(abs(x) for x in frames) < 0.7 * quietest_gun
        # The clank of the track links repeats about ten times a second.
        assert _rhythm(frames, rate, 75, 120) > 0.3
        # The owner then heard "a rainfall stick" and asked for "much lower frequency": the
        # mean frequency of the vehicle is low, far below a gun and below the footsteps.
        assert _mean_frequency(frames, rate) < 150
    steps, rate = _samples(sounds.make_sound(sounds.STEPS_SQUAD, 0))
    assert _mean_frequency(frames, rate) < 0.3 * _mean_frequency(steps, rate)
    # A plain rumble (filtered noise) has no such rhythm, so the check means something.
    rng = random.Random(1)
    state = 0.0
    rumble = array("h")
    for _ in range(int(2.2 * 22050)):
        state += 0.05 * (rng.uniform(-1, 1) - state)
        rumble.append(int(state * 30000))
    assert _rhythm(rumble, 22050, 75, 120) < 0.15
    # Its cues play softer than fire.
    units = {7: {"id": 7, "kind": "vehicle", "type": "T34", "hex": "E5", "nationality": "russian"}}
    move = {"rule_id": "30.2", "kind": "vehicle_move", "data": {"unit": 7, "from": "E5", "to": "E6"}}
    assert sounds.sound_cues(move, units)[0][2] <= 0.6 * 0.8
