"""The rule defects a source review found after the conformance suite was already green.

Each test names the condition and the result the rule text gives. The dice come from the
harness, which searches for a generator state. No result in this file is copied from a
run of the old code.
"""

from __future__ import annotations

from slcore import geometry
from slcore.game import FireGroup, State
from slcore.rules import r10_resolution, r11_terrain, r34_afv_vs_infantry

from conformance.harness import build_case, build_engine


def _fire(case: dict) -> tuple:
    built = build_case(case)
    events = []
    for payload in case.get("apply", []):
        built.state, evs = built.engine.apply(built.state, built.command(payload))
        events.extend(evs)
    return built, events


def test_canister_reaches_a_hex_past_the_target():
    """Rule 34.9: canister has a penetration factor of three, so the walk does not stop at the target."""
    built = build_case({
        "phase": "prep_fire",
        "sub_step": "fire_window",
        "phasing": "german",
        "active": "german",
        "dice": [6, 6],
        "units": [
            {"ref": "tank", "side": "german", "type": "MkIVF1", "hex": "A1", "facing": 0},
            {"ref": "near", "side": "russian", "type": "4-4-7", "hex": "A2"},
            {"ref": "far", "side": "russian", "type": "4-4-7", "hex": "A4"},
        ],
    })
    _, events = r34_afv_vs_infantry.resolve_effect(
        built.engine.armor_ctx,
        built.engine.fire_ctx,
        built.state,
        built.unit("tank"),
        geometry.parse_hex_id("A2"),
        r34_afv_vs_infantry.CANISTER_FIREPOWER * 2,
        built.state.phase,
        "34.2",
        r34_afv_vs_infantry.CANISTER_PENETRATION,
    )
    assert any(e.kind == "penetration" and e.data.get("target") == "A4" for e in events)
    assert built.unit("far").dm or any(
        e.kind == "fire_result" and built.unit("far").id in e.data.get("units", []) for e in events
    )


def test_penetration_spends_an_empty_hex():
    """Rule 17.5: a penetration of 2 reaches one hex past the target and stops.

    The hex in between is empty, and it still spends a factor. The squad in the hex
    after that takes no fire.
    """
    built, events = _fire({
        "phase": "prep_fire",
        "sub_step": "fire_window",
        "phasing": "german",
        "active": "german",
        "dice": [6, 6],
        "units": [
            {"ref": "s", "side": "german", "type": "4-6-7", "hex": "A1"},
            {"ref": "lmg", "side": "german", "type": "LMG", "carrier": "s"},
            {"ref": "near", "side": "russian", "type": "4-4-7", "hex": "A2"},
            {"ref": "far", "side": "russian", "type": "4-4-7", "hex": "A4"},
        ],
        "apply": [
            {"action": "group_add_weapon", "units": ["s"], "weapon": "lmg", "hex": "A2"},
            {"action": "group_fire"},
        ],
    })
    assert built.unit("far").hex == geometry.parse_hex_id("A4")
    assert not any(e.kind == "fire_result" and built.unit("far").id in e.data.get("units", []) for e in events)
    assert not any(e.kind == "penetration" and e.data.get("target") == "A4" for e in events)


def test_a_wall_on_the_second_hexside_stops_penetration():
    """Rule 17.5 and the ruling QA-17.5a: a wall on the hexside the line is about to cross stops the shot.

    The line is F3, F4, F5, F6. The wall is between F5 and F6. The machine gun has
    factors enough to reach F6. The squad in F6 takes no fire.
    """
    built, events = _fire({
        "phase": "prep_fire",
        "sub_step": "fire_window",
        "phasing": "german",
        "active": "german",
        "dice": [6, 6],
        "units": [
            {"ref": "s", "side": "german", "type": "4-6-7", "hex": "F3"},
            {"ref": "hmg", "side": "german", "type": "HMG", "carrier": "s"},
            {"ref": "near", "side": "russian", "type": "4-4-7", "hex": "F4"},
            {"ref": "far", "side": "russian", "type": "4-4-7", "hex": "F6"},
        ],
        "apply": [
            {"action": "group_add_weapon", "units": ["s"], "weapon": "hmg", "hex": "F4"},
            {"action": "group_fire"},
        ],
    })
    assert not any(e.kind == "penetration" and e.data.get("target") == "F6" for e in events)
    assert not built.unit("far").dm


def test_penetration_keeps_the_smoke_die_of_the_first_group():
    """Rule 24.7: one smoke die belongs to the fire group. The hex beyond the target uses that die.

    The walk does not roll a second smoke die.
    """
    built, events = _fire({
        "phase": "prep_fire",
        "sub_step": "fire_window",
        "phasing": "german",
        "active": "german",
        "dice": [3, 3],
        "single_dice": False,
        "units": [
            {"ref": "s", "side": "german", "type": "4-6-7", "hex": "A1"},
            {"ref": "lmg", "side": "german", "type": "LMG", "carrier": "s"},
            {"ref": "aim", "side": "russian", "type": "4-4-7", "hex": "A2"},
            {"ref": "near", "side": "russian", "type": "4-4-7", "hex": "A3"},
        ],
        "smoke": [{"hex": "A2", "side": "german"}],
        "apply": [
            {"action": "group_add_weapon", "units": ["s"], "weapon": "lmg", "hex": "A2"},
            {"action": "group_fire"},
        ],
    })
    smoke = [e for e in events if e.kind == "smoke_modifier"]
    assert len(smoke) == 1
    value = smoke[0].data["value"]
    assert 1 <= value <= 6
    hit = [e for e in events if e.kind == "fire_result" and built.unit("near").id in e.data["units"]]
    assert hit
    # The fire dice are 3 and 3. The open hex beyond adds no terrain. The smoke die is the
    # only modifier, and it is the die already rolled for the group.
    assert hit[0].data["adjusted"] == 6 + value


def _effect_adjusted(units: list[dict]) -> int:
    built = build_case({
        "phase": "defensive_fire",
        "sub_step": "fire_window",
        "actor": "defender",
        "phasing": "german",
        "active": "russian",
        "dice": [4, 4],
        "units": units,
    })
    firer = built.unit("tank")
    target = geometry.parse_hex_id("F5")
    _, events = r34_afv_vs_infantry.resolve_effect(
        built.engine.armor_ctx,
        built.engine.fire_ctx,
        built.state,
        firer,
        target,
        16,
        built.state.phase,
        "34.2",
    )
    results = [e for e in events if e.kind == "fire_result"]
    assert results
    return results[0].data["adjusted"]


def test_a_vehicle_that_is_the_cover_cancels_open_ground():
    """Rules 32.2 and 32.7: a vehicle on the line of sight is the cover. The moved squad takes no minus two.

    The vehicle is next to the firer, so rule 32.3 adds no wall. The open-ground modifier
    is the only difference. The effect dice are 4 and 4.
    """
    tank = {"ref": "tank", "side": "russian", "type": "T34", "hex": "F3", "facing": 0}
    moved = {"ref": "moved", "side": "german", "type": "4-6-7", "hex": "F5", "moved": True}
    cover = {"ref": "cover", "side": "german", "type": "SdKfz251", "hex": "F4", "facing": 0}
    assert _effect_adjusted([tank, moved]) == 6
    assert _effect_adjusted([tank, cover, moved]) == 8


def test_a_state_from_before_has_no_anti_tank_shots():
    """A saved state with no at_shots key loads as an empty list. The hash then covers the count."""
    engine = build_engine()
    document = engine.new_game(1).to_dict()
    assert document["at_shots"] == []
    del document["at_shots"]
    loaded = State.from_dict(document)
    assert loaded.at_shots == ()
    unit = loaded.units[0].to_dict()
    del unit["manned_mg"]
    back = type(loaded.units[0]).from_dict(unit)
    assert back.manned_mg is False


def test_penetration_uses_the_hex_before_the_step():
    """The wall test above is the play of the rule. This one checks the walk itself.

    previous starts at the target. The pair on the second step is the empty hex and the
    hex beyond it, which is where the wall sits.
    """
    engine = build_engine()
    firer = geometry.parse_hex_id("F3")
    target = geometry.parse_hex_id("F4")
    ray = engine.los.ray(firer, target)
    assert [geometry.hex_id(*h) for h in ray[:2]] == ["F5", "F6"]
    ctx = engine.fire_ctx
    assert r10_resolution.penetration_continues(ctx, ray[0], ray[1]) is False
    group = FireGroup(target, ((0, 1),), None)
    assert group.target == target


def test_a_flamethrower_in_defensive_fire_takes_no_open_ground_modifier():
    """Rule 22.2: no modifier of any kind, so no minus two of rule 16.5 against a mover.

    The Russian squad moved in the open next to the German engineer. The flamethrower
    fires in the Defensive Fire Phase with dice 3 and 3, so the adjusted roll stays 6.
    """
    built, events = _fire({
        "phase": "defensive_fire",
        "sub_step": "fire_window",
        "actor": "defender",
        "phasing": "russian",
        "active": "german",
        "dice": [3, 3],
        "units": [
            {"ref": "e", "side": "german", "type": "8-3-8", "hex": "C2"},
            {"ref": "ft", "side": "german", "type": "FT", "carrier": "e"},
            {"ref": "t", "side": "russian", "type": "4-4-7", "hex": "D2", "moved": True},
        ],
        "apply": [{"action": "ft_fire", "units": ["e"], "weapon": "ft", "hex": "D2"}],
    })
    target = geometry.parse_hex_id("D2")
    assert r11_terrain.moving_in_open_modifier(built.engine.board, target) != 0
    hit = [e for e in events if e.kind == "fire_result" and built.unit("t").id in e.data["units"]]
    assert hit
    assert hit[0].data["adjusted"] == 6
