"""The kind of fire of each event, for its animation: rifles, SMG, machine gun, flame, rocket,
tank gun, demolition charge, smoke, grenades, overrun.

The events are real: scripted agents play scenarios 1, 2, and 4 through the engine, and the
unit documents come from the spectator view of the state after each command. No Panda3D.
"""

from __future__ import annotations

from collections import Counter

from slcli.play import build_engine, make_agent
from slcore import view as core_view
from slwindow3d.firekinds import (
    BLAST,
    FLAME,
    GRENADES,
    GUN,
    MACHINE_GUNS,
    MG,
    OVERRUN,
    RIFLE,
    ROCKET,
    SMG,
    SMOKE,
    shots_for,
)


def _events(scenario: str, agent: str, seeds, limit: int = 3000):
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


def _check_fire(event, units, seen: Counter) -> None:
    shots = shots_for(event, units)
    members = event["data"]["members"]
    assert len(shots) == len(members)
    for member, shot in zip(members, shots):
        seen[shot.kind] += 1
        weapon = member.get("weapon")
        if weapon is not None:
            name = units[weapon]["type"]
            if name in MACHINE_GUNS:
                assert shot.kind == MG and shot.size == MACHINE_GUNS[name]
            elif name == "FT":
                assert shot.kind == FLAME
            continue
        if event["rule_id"] == "22.2":
            assert shot.kind == FLAME
            continue
        squad = units[member["unit"]]
        if squad["type"] == "6-2-8":
            assert shot.kind == SMG
        if squad["type"] == "4-6-7":
            assert shot.kind == RIFLE
        assert shot.source == squad["hex"]
        assert shot.target == event["data"]["target"]


def test_infantry_fire_is_rifles_smg_and_machine_guns_by_the_firing_unit():
    seen: Counter = Counter()
    for event, units in _events("s01_guards_counterattack", "v1", range(2)):
        if event["kind"] == "fire":
            _check_fire(event, units, seen)
    assert seen[RIFLE] and seen[SMG] and seen[MG]


def test_the_engineers_scenario_has_fire_and_smoke_of_its_own_kinds():
    seen: Counter = Counter()
    for event, units in _events("s02_tractor_works", "v2", range(2)):
        if event["kind"] == "fire":
            _check_fire(event, units, seen)
        for shot in shots_for(event, units):
            seen[shot.kind] += 1
            if event["kind"] == "smoke":
                assert shot.kind == SMOKE and shot.target == event["data"]["hex"]
            if event["kind"] in ("cc_kill", "cc_miss") and shot.target:
                assert shot.kind == GRENADES
    assert seen[MG] and seen[SMOKE]


def test_tank_guns_and_rockets_by_their_events():
    seen: Counter = Counter()
    for event, units in _events("s04_armor_probe", "v3", range(4)):
        for shot in shots_for(event, units):
            seen[shot.kind] += 1
            if event["kind"] == "to_hit":
                assert shot.kind == GUN and shot.hit == event["data"]["hit"]
                assert shot.source == units[event["data"]["unit"]]["hex"]
            if event["kind"] == "at_to_hit":
                assert shot.kind == ROCKET
                assert shot.target == units[event["data"]["vehicle"]]["hex"]
    # The tanks keep four hexes from enemy infantry (`armor.py`), out of panzerfaust range,
    # so these games may have no rocket; the shape test below reads the rocket.
    assert seen[GUN]


def test_the_events_of_the_rare_weapons_by_their_shape_in_the_engine():
    """A flamethrower fire is a "fire" event of rule 22.2, and a demolition charge is a
    "demo_explode" event; the shapes are those `engine.py` makes."""
    units = {1: {"id": 1, "type": "8-3-8", "hex": "C3", "range": 3}, 2: {"id": 2, "type": "FT", "hex": "C3"}, 7: {"id": 7, "type": "MkIVF2", "hex": "E5"}}
    flame = {"rule_id": "22.2", "kind": "fire", "data": {"target": "D3", "members": [{"unit": 1, "weapon": 2, "halves": 48, "modifiers": []}]}}
    assert [s.kind for s in shots_for(flame, units)] == [FLAME]
    blast = {"rule_id": "23.1", "kind": "demo_explode", "data": {"charge": 0, "hex": "D3", "firepower": 30}}
    assert [(s.kind, s.target) for s in shots_for(blast, units)] == [(BLAST, "D3")]
    units[3] = {"id": 3, "type": "4-6-7", "hex": "E3", "range": 6, "nationality": "german"}
    units[4] = {"id": 4, "type": "PF", "hex": "E3"}
    rocket = {"rule_id": "37.3", "kind": "at_to_hit", "data": {"unit": 3, "weapon": 4, "vehicle": 7, "hit": True}}
    assert [(s.kind, s.source, s.target, s.hit) for s in shots_for(rocket, units)] == [(ROCKET, "E3", "E5", True)]
    overrun = {"rule_id": "35.1", "kind": "overrun", "data": {"unit": 7, "hex": "E6"}}
    assert [(s.kind, s.target) for s in shots_for(overrun, units)] == [(OVERRUN, "E6")]
    dischargers = {"rule_id": "41.4", "kind": "smoke_dischargers", "data": {"unit": 7, "hex": "E5"}}
    assert [(s.kind, s.source, s.target) for s in shots_for(dischargers, units)] == [(SMOKE, None, "E5")]
    # An event of a unit the view does not hold still shows on its target.
    hidden = {"rule_id": "10.6", "kind": "fire", "data": {"target": "D3", "members": [{"unit": 99, "weapon": None}]}}
    assert [(s.kind, s.source, s.target) for s in shots_for(hidden, units)] == [(RIFLE, None, "D3")]
    assert shots_for({"rule_id": "5.5", "kind": "move", "data": {}}, units) == []


def test_each_shot_names_the_army_of_the_unit_that_fired():
    armies = set()
    for event, units in _events("s01_guards_counterattack", "v1", range(1)):
        if event["kind"] != "fire":
            continue
        for member, shot in zip(event["data"]["members"], shots_for(event, units)):
            assert shot.army == units[member["unit"]]["nationality"]
            armies.add(shot.army)
    assert armies == {"german", "russian"}


def test_the_tracers_have_the_historical_colour_of_each_army():
    """The owner's rule: American and British tracers were most often red; German and
    Russian tracers were most often green, and some were white or yellow."""
    import colorsys
    import random

    from slwindow3d.effects import PALE_SHARE, TRACER_PALE, tracer_colour

    def hue(colour):
        return colorsys.rgb_to_hls(*colour)[0]

    for army in ("american", "british"):
        for weapon in ("rifle", "smg", "mg"):
            colour = tracer_colour(army, weapon, random.Random(1))
            assert hue(colour) < 0.03 or hue(colour) > 0.97, f"{army} {weapon} tracer is not red: {colour}"
            assert colour[0] > 2 * colour[1], f"{army} {weapon} tracer reads pink, not red: {colour}"
    for army in ("german", "russian"):
        assert 0.28 < hue(tracer_colour(army, "mg")) < 0.39, "a green tracer"
        rng = random.Random(7)
        rounds = [tracer_colour(army, "mg", rng) for _ in range(2000)]
        pale = sum(1 for c in rounds if c in TRACER_PALE)
        assert abs(pale / len(rounds) - PALE_SHARE) < 0.04
        assert all(c in TRACER_PALE or 0.28 < hue(c) < 0.39 for c in rounds)
    # A red army never fires a pale round.
    rng = random.Random(3)
    assert not any(tracer_colour("american", "mg", rng) in TRACER_PALE for _ in range(500))
    # A machine gun tracer is deeper than a rifle tracer of the same army.
    assert colorsys.rgb_to_hls(*tracer_colour("german", "mg"))[1] < colorsys.rgb_to_hls(*tracer_colour("german", "rifle"))[1]
    # A unit with no army in the view keeps the plain tracer colours.
    assert tracer_colour("", "mg") not in (tracer_colour("german", "mg"), tracer_colour("american", "mg"))
