"""A1 to A12 of the review of 2026-09-23, with PR-14, PR-21, and PR-43 to PR-53.

Each test builds the rule situation with the conformance harness and plays real commands
through the real engine. The dice come from the harness search, so no test holds a seed
that it found by hand.
"""

from __future__ import annotations

from slcore import geometry
from slcore.commands import Command
from slcore.los_eval import thread_hexes
from slcore.rules import r28_vehicles, r30_vehicle_movement, r32_afv_cover, r33_afv_combat, r42_hidden
from slcore.rules.r30_vehicle_movement import VehicleContext
from slcore.state import Board, Hex, default_polygons
from sldata.loaders import load_hexsides, load_terrain

from conformance.harness import build_case, build_engine

P = geometry.parse_hex_id


def payloads(cs) -> list[dict]:
    return [lc.payload for lc in cs.engine.legal_commands(cs.state).commands]


def of_action(cs, action: str) -> list[dict]:
    return [p for p in payloads(cs) if p["action"] == action]


def apply(cs, payload: dict) -> list[dict]:
    cs.state, events = cs.engine.apply(cs.state, cs.command(payload))
    return [e.to_dict() for e in events]


def end_phase(cs) -> list[dict]:
    return apply(cs, {"action": "end_phase"})


def kinds(events: list[dict]) -> list[tuple[str, str]]:
    return [(e["rule_id"], e["kind"]) for e in events]


def fire_case(units: list[dict], phasing: str = "german", phase: str = "prep_fire", **extra) -> dict:
    case = {"phase": phase, "sub_step": "fire_window", "phasing": phasing, "units": units}
    case.update(extra)
    return case


# ------------------------------------------------------------------ A1: line of sight


def test_a_panzerfaust_does_not_fire_through_a_stone_building():
    """A1: rule 8.1 with rule 37. E5 is a stone building between D5 and F5."""
    cs = build_case(
        fire_case(
            [
                {"ref": "s", "side": "german", "type": "4-6-7", "hex": "D5"},
                {"ref": "pf", "side": "german", "type": "PF", "carrier": "s"},
                {"ref": "t", "side": "russian", "type": "T34", "hex": "F5", "facing": 0},
            ]
        )
    )
    assert not cs.engine._can_see(cs.state, P("D5"), P("F5"))
    assert of_action(cs, "at_fire") == []


def test_a_panzerfaust_fires_along_a_clear_line():
    """A1: the same weapon in the open at two hexes has its shot."""
    cs = build_case(
        fire_case(
            [
                {"ref": "s", "side": "german", "type": "4-6-7", "hex": "A7"},
                {"ref": "pf", "side": "german", "type": "PF", "carrier": "s"},
                {"ref": "t", "side": "russian", "type": "T34", "hex": "A9", "facing": 0},
            ]
        )
    )
    assert of_action(cs, "at_fire") == [{"action": "at_fire", "units": [cs.ids["s"]], "weapon": cs.ids["pf"], "hex": "A9"}]


# ------------------------------------------------------------------ A2: the Prep Fire mark


def test_a_panzerfaust_shot_in_prep_fire_leaves_the_prep_fire_counter():
    """A2 and PR-43: the squad that fired a panzerfaust does not move or fire again."""
    cs = build_case(
        fire_case(
            [
                {"ref": "s", "side": "german", "type": "4-6-7", "hex": "A7"},
                {"ref": "pf", "side": "german", "type": "PF", "carrier": "s"},
                {"ref": "t", "side": "russian", "type": "T34", "hex": "A9", "facing": 0},
            ]
        )
    )
    apply(cs, {"action": "at_fire", "units": ["s"], "weapon": "pf", "hex": "A9"})
    assert cs.state.units[cs.ids["pf"]].eliminated
    while cs.state.phase == "prep_fire":
        end_phase(cs)
    assert cs.state.phase == "movement"
    assert cs.unit("s").prep_fired
    assert not any(p["action"] in ("move", "stack_move") and cs.ids["s"] in p.get("units", []) for p in payloads(cs))


def test_a_squad_fires_a_panzerfaust_after_its_group_fire():
    """PR-43: the sequence of the group fire and the anti-tank shot does not matter."""
    cs = build_case(
        fire_case(
            [
                {"ref": "s", "side": "german", "type": "4-6-7", "hex": "A7"},
                {"ref": "pf", "side": "german", "type": "PF", "carrier": "s"},
                {"ref": "t", "side": "russian", "type": "T34", "hex": "A9", "facing": 0},
                {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "B7"},
            ]
        )
    )
    shot = {"action": "at_fire", "units": [cs.ids["s"]], "weapon": cs.ids["pf"], "hex": "A9"}
    assert shot in payloads(cs)
    apply(cs, {"action": "group_add", "units": ["s"], "hex": "B7"})
    apply(cs, {"action": "group_fire"})
    assert cs.unit("s").fired
    assert shot in payloads(cs)


# ------------------------------------------------------------------ A3 and A5: rule 34.8


def exposed_case(squad_hex: str, phase: str = "defensive_fire", extra_units: list[dict] | None = None, **kw) -> dict:
    units = [
        {"ref": "s", "side": "german", "type": "4-6-7", "hex": squad_hex},
        {"ref": "t", "side": "russian", "type": "MkIVF2", "army": "german", "hex": "C7", "facing": 0, "crew_exposed": True},
        {"ref": "c", "side": "russian", "type": "2-3-7", "crew_of": "t"},
    ]
    units.extend(extra_units or [])
    return fire_case(units, phasing="russian", phase=phase, **kw)


def test_no_immobilize_attempt_from_a_far_hex_on_an_exposed_crew():
    """A3: rule 36.12 keeps its adjacency and cover. Rule 34.8 is fire on the crew."""
    cs = build_case(exposed_case("J9"))
    assert of_action(cs, "afv_attack") == []
    assert not any(p.get("hex") == "C7" for p in payloads(cs))


def test_an_exposed_crew_is_a_fire_group_target_in_range_and_sight():
    """A3 and PR-44: the hex of the vehicle is a target of an infantry fire group."""
    cs = build_case(exposed_case("C9"))
    assert {"action": "group_add", "units": [cs.ids["s"]], "hex": "C7"} in payloads(cs)
    assert of_action(cs, "afv_attack") == []


def test_a_kia_on_the_exposed_crew_can_abandon_the_vehicle():
    """A3 and PR-44: the same roll with plus two, a KIA, and a failed crew morale check."""
    cs = build_case(
        exposed_case(
            "C8",
            extra_units=[{"ref": "s2", "side": "german", "type": "4-6-7", "hex": "C8"}],
            dice=[1, 1, 6, 6],
        )
    )
    apply(cs, {"action": "group_add", "units": ["s"], "hex": "C7"})
    apply(cs, {"action": "group_add", "units": ["s2"], "hex": "C7"})
    events = apply(cs, {"action": "group_fire"})
    crew = next(e for e in events if e["kind"] == "crew_fire")
    assert crew["rule_id"] == "34.8"
    assert crew["data"]["firepower"] == 16
    assert crew["data"]["adjusted"] == 4
    assert crew["data"]["result"] == "KIA"
    assert ("34.8", "crew_abandons") in kinds(events)
    assert cs.unit("t").wreck
    assert cs.unit("c").hex == P("C7")


def test_a_morale_result_on_the_exposed_crew_is_ignored():
    """Rule 34.8: morale check results are ignored."""
    cs = build_case(exposed_case("C9", dice=[4, 4]))
    apply(cs, {"action": "group_add", "units": ["s"], "hex": "C7"})
    events = apply(cs, {"action": "group_fire"})
    crew = next(e for e in events if e["kind"] == "crew_fire")
    assert crew["data"]["result"] != "KIA"
    assert not any(e["kind"] in ("crew_morale", "crew_abandons") for e in events)
    assert not cs.unit("t").wreck


def test_the_exposed_counter_of_the_phasing_side_comes_off_after_defensive_fire():
    """A5: the vehicle exposed its crew in its own Prep Fire Phase. The enemy phase is this one."""
    cs = build_case(
        fire_case(
            [{"ref": "t", "side": "german", "type": "MkIVF2", "hex": "C7", "facing": 0, "crew_exposed": True}],
            phasing="german",
            phase="defensive_fire",
        )
    )
    events = end_phase(cs)
    assert ("34.8", "crew_inside") in kinds(events)
    assert not cs.unit("t").crew_exposed


def test_the_exposed_counter_of_the_defender_lasts_into_advancing_fire():
    """A5: the defender exposed its crew in the Defensive Fire Phase, and the next enemy
    fire phase is the Advancing Fire Phase of the same player turn."""
    cs = build_case(
        fire_case(
            [{"ref": "t", "side": "russian", "type": "T34", "hex": "C7", "facing": 0, "crew_exposed": True}],
            phasing="german",
            phase="defensive_fire",
        )
    )
    end_phase(cs)
    assert cs.state.phase == "advancing_fire"
    assert cs.unit("t").crew_exposed
    events = end_phase(cs)
    assert ("34.8", "crew_inside") in kinds(events)
    assert not cs.unit("t").crew_exposed


# ------------------------------------------------------------------ A4: rule 32.3


def test_each_vehicle_on_the_line_is_a_wall_of_its_own():
    """A4: a second vehicle behind the first does not clear the block of the first."""
    engine = build_engine()
    firer, target = P("A1"), P("A7")
    traced = thread_hexes(engine.los, firer, target)
    first, last = traced[2], traced[-1]
    assert r32_afv_cover.vehicle_block(engine.board, frozenset({first}), firer, traced, target) == (True, 0)
    assert r32_afv_cover.vehicle_block(engine.board, frozenset({first, last}), firer, traced, target) == (True, 0)
    assert r32_afv_cover.vehicle_block(engine.board, frozenset({last}), firer, traced, target) == (False, 2)


# ------------------------------------------------------------------ A6: rule 33.32


def test_an_unmodified_two_reads_the_third_die_against_the_final_number():
    """A6: the final number is below 2 only after the modifiers, and the third die hits."""
    cs = build_case(
        fire_case(
            [
                {"ref": "t", "side": "german", "type": "MkIVF2", "hex": "A1", "facing": 3},
                {"ref": "e", "side": "russian", "type": "T34", "hex": "A2", "facing": 0},
            ],
            dice=[1, 1, 3],
            single_dice=True,
        )
    )
    engine = cs.engine
    firer = cs.unit("t")
    # Row 7 of a hull down vehicle at 1 hex needs 7. Case D plus a modifier of 6 makes the
    # final number -1, so the third die hits on 1 or 2 and misses on 3.
    state, result = r33_afv_combat.roll_to_hit(engine.armor_ctx, cs.state, firer, P("A2"), "vehicle_hull_down", (), 8)
    assert result.raw == 2 and result.needed == 7 and result.modifier == 8
    assert result.third_die == 3
    assert not result.hit
    cs2 = build_case(
        fire_case(
            [
                {"ref": "t", "side": "german", "type": "MkIVF2", "hex": "A1", "facing": 3},
                {"ref": "e", "side": "russian", "type": "T34", "hex": "A2", "facing": 0},
            ],
            dice=[1, 1, 2],
            single_dice=True,
        )
    )
    state, result = r33_afv_combat.roll_to_hit(engine.armor_ctx, cs2.state, cs2.unit("t"), P("A2"), "vehicle_hull_down", (), 8)
    assert result.third_die == 2 and result.hit


# ------------------------------------------------------------------ A7: rule 22 on a vehicle


def ft_case(squad: str = "8-3-8", **kw) -> dict:
    return fire_case(
        [
            {"ref": "s", "side": "german", "type": squad, "hex": "A7"},
            {"ref": "ft", "side": "german", "type": "FT", "carrier": "s"},
            {"ref": "t", "side": "russian", "type": "T34", "hex": "A8", "facing": 0},
            {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "A8"},
        ],
        **kw,
    )


def test_only_an_assault_engineer_fires_a_flamethrower_at_a_vehicle():
    """A7 and rule 22.4."""
    assert of_action(build_case(ft_case("4-6-7")), "at_fire") == []
    cs = build_case(ft_case())
    assert of_action(cs, "at_fire") == [{"action": "at_fire", "units": [cs.ids["s"]], "weapon": cs.ids["ft"], "hex": "A8"}]


def test_no_flamethrower_shot_at_a_vehicle_from_a_melee_hex():
    """A7: a unit in a melee hex does not fire out of it."""
    cs = build_case(ft_case(melee=["A7"]))
    assert of_action(cs, "at_fire") == []


def test_the_flamethrower_roll_is_the_kill_roll_the_infantry_roll_and_the_fuel_roll():
    """A7 and PR-47: one roll of 10 kills nothing, burns the infantry with no modifier,
    and empties the fuel."""
    cs = build_case(ft_case(dice=[5, 5]))
    events = apply(cs, {"action": "at_fire", "units": ["s"], "weapon": "ft", "hex": "A8"})
    kill = next(e for e in events if e["kind"] == "kill_roll")
    assert kill["data"]["raw"] == 10 and not kill["data"]["killed"]
    burn = next(e for e in events if e["kind"] == "flamethrower_infantry")
    assert burn["data"]["roll"] == 10 and burn["data"]["adjusted"] == 10 and burn["data"]["modifiers"] == []
    result = next(e for e in events if e["kind"] == "fire_result")
    assert result["data"]["adjusted"] == 10
    assert ("22.6", "out_of_fuel") in kinds(events)
    assert cs.unit("ft").eliminated
    assert sum(1 for e in events if e["kind"] in ("kill_roll",)) == 1


# ------------------------------------------------------------------ A8: the dud charge


def test_a_dud_charge_lies_in_the_placement_hex_and_never_arms():
    """A8 and PR-14: one dud event, the charge on the ground, and no later arming."""
    cs = build_case(
        {
            "phase": "defensive_fire",
            "sub_step": "fire_window",
            "phasing": "german",
            "units": [
                {"ref": "e", "side": "german", "type": "8-3-8", "hex": "B7", "broken": True},
                {"ref": "dc", "side": "german", "type": "DC"},
                {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "B8"},
            ],
            "demo": [{"side": "german", "hex": "B8", "placer": "e", "from": "B7", "weapon": "dc"}],
        }
    )
    events = end_phase(cs)
    assert kinds(events).count(("23.3", "demo_dud")) == 1
    assert cs.state.demo == ()
    assert cs.unit("dc").hex == P("B7") and cs.unit("dc").carrier is None and not cs.unit("dc").eliminated
    later: list[dict] = []
    for _ in range(40):
        if cs.state.game_over or cs.state.turn > 2:
            break
        later.extend(end_phase(cs) if of_action(cs, "end_phase") else apply(cs, payloads(cs)[0]))
    assert ("23.3", "demo_dud") not in kinds(later)
    assert ("23.3", "demo_armed") not in kinds(later)


# ------------------------------------------------------------------ A9: the facing on entry


def test_a_vehicle_names_any_facing_in_the_hex_it_enters():
    """A9 and PR-21: rule 30.5 gives a free facing change after a move into a hex."""
    cs = build_case(
        {
            "phase": "movement",
            "sub_step": "move_window",
            "phasing": "german",
            "units": [{"ref": "t", "side": "german", "type": "MkIVF2", "hex": "B2", "facing": 3}],
        }
    )
    into = [p for p in of_action(cs, "vehicle_move") if p["hex"] == "B3"]
    assert sorted(p["facing"] for p in into) == [0, 1, 2, 3, 4, 5]
    events = apply(cs, {"action": "vehicle_move", "units": ["t"], "hex": "B3", "facing": 5})
    assert cs.unit("t").facing == 5
    assert not cs.unit("t").pivoted
    assert events[0]["data"]["facing"] == 5


# ------------------------------------------------------------------ A10: HEAT and the charge


def heat_case(**kw) -> dict:
    return fire_case(
        [
            {"ref": "p", "side": "russian", "army": "american", "type": "Priest", "hex": "A1", "facing": 2},
            {"ref": "e", "side": "german", "type": "MkIVF2", "hex": "A4", "facing": 0},
            {"ref": "g", "side": "german", "type": "4-6-7", "hex": "A3"},
        ],
        phasing="russian",
        **kw,
    )


def test_a_gun_marked_h6_fires_heat_at_a_vehicle_and_not_at_infantry():
    """A10 and PR-45: rule 63.3."""
    cs = build_case(heat_case())
    shots = [p for p in of_action(cs, "afv_fire") if p["units"] == [cs.ids["p"]]]
    assert {"action": "afv_fire", "units": [cs.ids["p"]], "hex": "A4", "aim": "vehicle", "ammo": "heat"} in shots
    assert not any(p["ammo"] == "heat" and p["aim"] == "infantry" for p in shots)


def test_a_heat_hit_reads_the_h6_column():
    """A10: a to-hit roll of 4 hits and keeps the HEAT."""
    cs = build_case(heat_case(dice=[2, 2, 1, 1]))
    events = apply(cs, {"action": "afv_fire", "units": ["p"], "hex": "A4", "aim": "vehicle", "ammo": "heat"})
    kill = next(e for e in events if e["kind"] == "kill_roll")
    assert kill["data"]["column"] == "h6"
    assert not cs.unit("p").heat_spent


def test_a_heat_roll_of_six_spends_the_heat_and_the_shot_is_high_explosive():
    """A10 and rule 63.32."""
    cs = build_case(heat_case(dice=[3, 3, 1, 1]))
    events = apply(cs, {"action": "afv_fire", "units": ["p"], "hex": "A4", "aim": "vehicle", "ammo": "heat"})
    assert ("63.32", "heat_spent") in kinds(events)
    kill = next(e for e in events if e["kind"] == "kill_roll")
    assert kill["data"]["column"] == "he105"
    assert cs.unit("p").heat_spent
    assert not any(p.get("ammo") == "heat" for p in of_action(cs, "afv_fire"))


def test_a_demolition_charge_attacks_the_vehicle_of_its_hex():
    """A10 and PR-46: the explosion roll on the demolition charge column, and on the
    Infantry Fire Table against the infantry below the vehicle."""
    cs = build_case(
        {
            "phase": "advancing_fire",
            "sub_step": "demo_window",
            "phasing": "german",
            "dice": [2, 2],
            "units": [
                {"ref": "e", "side": "german", "type": "8-3-8", "hex": "B7"},
                {"ref": "dc", "side": "german", "type": "DC"},
                {"ref": "t", "side": "russian", "type": "T34", "hex": "B8", "facing": 0},
                {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "B8"},
            ],
            "demo": [{"side": "german", "hex": "B8", "placer": "e", "from": "B7", "weapon": "dc", "armed": True}],
        }
    )
    charge = cs.state.demo[0].id
    events = apply(cs, {"action": "explode_demo", "hex": "B8", "charge": charge})
    kill = next(e for e in events if e["kind"] == "kill_roll")
    assert kill["data"]["column"] == "demolition_charge"
    assert kill["data"]["raw"] == 4 and kill["data"]["killed"]
    assert cs.unit("t").wreck
    assert any(e["kind"] == "fire_result" for e in events)


def test_a_charge_that_malfunctions_does_not_touch_the_vehicle():
    """Rule 23.8: an unmodified 12 is a malfunction."""
    cs = build_case(
        {
            "phase": "advancing_fire",
            "sub_step": "demo_window",
            "phasing": "german",
            "dice": [6, 6],
            "units": [
                {"ref": "e", "side": "german", "type": "8-3-8", "hex": "B7"},
                {"ref": "dc", "side": "german", "type": "DC"},
                {"ref": "t", "side": "russian", "type": "T34", "hex": "B8", "facing": 0},
            ],
            "demo": [{"side": "german", "hex": "B8", "placer": "e", "from": "B7", "weapon": "dc", "armed": True}],
        }
    )
    events = apply(cs, {"action": "explode_demo", "hex": "B8", "charge": cs.state.demo[0].id})
    assert not any(e["kind"] == "kill_roll" for e in events)
    assert not cs.unit("t").wreck


# ------------------------------------------------------------------ A11: tank smoke


def test_tank_smoke_goes_only_where_the_gun_sees():
    """A11 and PR-48: no smoke through the stone building of E5."""
    cs = build_case(
        fire_case(
            [{"ref": "t", "side": "german", "type": "MkIVF2", "hex": "C5", "facing": 2}],
            smoke_left={"german": 1},
        )
    )
    hexes = {p["hex"] for p in of_action(cs, "afv_smoke")}
    assert hexes
    for hex_id in hexes:
        assert cs.engine._can_see(cs.state, P("C5"), P(hex_id))
        assert geometry.distance(P("C5"), P(hex_id)) > 1
    assert "F5" not in hexes


def test_no_dischargers_with_no_smoke_counter_left():
    """A11 and PR-48: the dischargers take a counter from the allowance of rule 24.1."""
    units = [{"ref": "t", "side": "german", "type": "MkIVF2", "hex": "C7", "facing": 0}]
    assert of_action(build_case(fire_case(units, smoke_left={"german": 1})), "afv_dischargers")
    assert of_action(build_case(fire_case(units)), "afv_dischargers") == []


# ------------------------------------------------------------------ A12


def test_a_hidden_vehicle_is_in_no_legal_list_of_the_other_side():
    """A12 and PR-49."""
    cs = build_case(
        fire_case(
            [
                {"ref": "s", "side": "german", "type": "4-6-7", "hex": "A7"},
                {"ref": "pf", "side": "german", "type": "PF", "carrier": "s"},
                {"ref": "g", "side": "german", "type": "MkIVF2", "hex": "A5", "facing": 3},
                {"ref": "t", "side": "russian", "type": "T34", "hex": "A9", "facing": 0, "hidden": True},
            ],
            phase="defensive_fire",
            phasing="russian",
        )
    )
    assert not any(p.get("hex") == "A9" for p in payloads(cs))


def test_an_afv_hides_only_in_woods_or_a_wood_building():
    """Rule 42.7 and PR-49."""
    engine = build_engine()
    sides = {0: "german", 1: "russian"}
    state = engine.new_game(1)
    tank = next(u for u in state.units if u.is_vehicle and u.player == 0)
    squad = next(u for u in state.units if u.kind == "squad" and u.player == 0)
    for hex_id, afv, infantry in (("E2", True, True), ("F8", True, True), ("C3", False, True), ("A1", False, False)):
        ref = P(hex_id)
        assert r42_hidden.can_hide("german", sides, engine.board, tank.with_(hex=ref)) is afv, hex_id
        assert r42_hidden.can_hide("german", sides, engine.board, squad.with_(hex=ref)) is infantry, hex_id


def test_case_h_reads_only_a_counter_of_the_target_side():
    """A12: the firer's own counter in the target hex conceals nothing of the enemy."""
    cs = build_case(
        fire_case(
            [
                {"ref": "t", "side": "german", "type": "MkIVF2", "hex": "A1", "facing": 3},
                {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "A5"},
            ],
            dice=[6, 6],
            concealment=[{"side": "german", "hex": "A5"}],
        )
    )
    events = apply(cs, {"action": "afv_fire", "units": ["t"], "hex": "A5", "aim": "infantry", "ammo": "he"})
    hit = next(e for e in events if e["kind"] == "to_hit")
    assert "H" not in hit["data"]["cases"]


def test_the_passengers_get_off_before_an_overrun():
    """A12 and rule 35.5: they stay in the hex the vehicle leaves."""
    cs = build_case(
        {
            "phase": "movement",
            "sub_step": "move_window",
            "phasing": "german",
            "units": [
                {"ref": "t", "side": "german", "type": "MkIVF2", "hex": "B2", "facing": 3},
                {"ref": "p", "side": "german", "type": "4-6-7", "riding": "t"},
                {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "B3"},
            ],
        }
    )
    events = apply(cs, {"action": "vehicle_move", "units": ["t"], "hex": "B3", "facing": 3})
    assert ("35.5", "dismount") in kinds(events)
    assert ("35.1", "overrun") in kinds(events)
    assert cs.unit("p").hex == P("B2") and not cs.unit("p").riding


def test_a_vehicle_overruns_a_dummy_counter_as_it_would_a_stack():
    """PR-31: the hex of an enemy counter is overrun whether a unit is below it or not."""
    cs = build_case(
        {
            "phase": "movement",
            "sub_step": "move_window",
            "phasing": "german",
            "units": [{"ref": "t", "side": "german", "type": "MkIVF2", "hex": "B2", "facing": 3}],
            "concealment": [{"side": "russian", "hex": "B3"}],
        }
    )
    events = apply(cs, {"action": "vehicle_move", "units": ["t"], "hex": "B3", "facing": 3})
    assert ("35.1", "overrun") in kinds(events)
    assert cs.unit("t").overran


def push_case(extra: list[dict] | None = None) -> dict:
    units = [
        {"ref": "t", "side": "german", "type": "MkIVF2", "hex": "B3", "facing": 3},
        {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "B3"},
    ]
    units.extend(extra or [])
    return {"phase": "defensive_fire", "sub_step": "fire_window", "phasing": "german", "units": units}


def test_the_owner_chooses_the_hex_of_the_push_out():
    """A12 and PR-51: a window after the Defensive Fire Phase with one command for each hex."""
    cs = build_case(push_case([{"ref": "g", "side": "german", "type": "4-6-7", "hex": "B4"}]))
    end_phase(cs)
    assert cs.engine.current_step(cs.state).name == "push_out"
    assert cs.engine.scenario.players()[cs.state.active] == "russian"
    options = of_action(cs, "push_out")
    hexes = sorted(p["hex"] for p in options)
    assert "B4" not in hexes
    assert hexes == sorted(geometry.hex_id(*h) for h in cs.engine.board.neighbors(P("B3")) if h != P("B4"))
    assert of_action(cs, "end_phase") == []
    apply(cs, {"action": "push_out", "units": ["r"], "hex": "C3"})
    assert cs.unit("r").hex == P("C3")
    end_phase(cs)
    assert cs.state.phase == "advancing_fire"


def test_the_push_out_obeys_the_stacking_limit():
    """PR-51: a hex where the unit would break rule 6.1 is no choice."""
    full = [{"ref": f"x{i}", "side": "russian", "type": "4-4-7", "hex": "C3"} for i in range(3)]
    cs = build_case(push_case(full))
    end_phase(cs)
    assert "C3" not in {p["hex"] for p in of_action(cs, "push_out")}


def test_a_unit_with_no_hex_to_step_into_is_eliminated():
    """Rule 35.8: the enemy is around the hex."""
    ring = [
        {"ref": f"g{i}", "side": "german", "type": "4-6-7", "hex": geometry.hex_id(*h)}
        for i, h in enumerate(sorted(geometry.neighbors(*P("B3"))))
        if h in build_engine().board
    ]
    cs = build_case(push_case(ring))
    end_phase(cs)
    assert cs.engine.current_step(cs.state).name == "push_out"
    assert of_action(cs, "push_out") == []
    events = end_phase(cs)
    assert ("35.8", "crushed") in kinds(events)
    assert cs.unit("r").eliminated


def road_board(named: bool) -> Board:
    """Three road hexes that touch in a triangle, B2 to C2 to C3, with the road only on
    B2 to C2 and C2 to C3 when the document names the hexsides."""
    terrain = load_terrain()
    roads = {"B2", "C2", "C3"}
    sides = {"B2": (), "C2": (), "C3": ()}
    if named:
        b2, c2, c3 = P("B2"), P("C2"), P("C3")
        sides = {
            "B2": (geometry.direction_to(b2, c2),),
            "C2": tuple(sorted((geometry.direction_to(c2, b2), geometry.direction_to(c2, c3)))),
            "C3": (geometry.direction_to(c3, c2),),
        }
    hexes = []
    for col in range(4):
        first = 0 if col & 1 else 1
        for row in range(first, 5):
            hid = geometry.hex_id(col, row)
            hexes.append(
                Hex(col=col, row=row, road=hid in roads, road_sides=sides.get(hid, ()), polygons=default_polygons(col, row, "open", terrain))
            )
    return Board(4, 4, hexes, terrain, name="roads")


def test_the_road_rate_needs_the_road_on_the_hexside():
    """A12 and PR-50: B2 and C3 touch, and the road does not cross their hexside."""
    assert geometry.direction_to(P("B2"), P("C3")) is not None
    engine = build_engine()
    for named, expected in ((True, False), (False, True)):
        board = road_board(named)
        ctx = VehicleContext(board, load_terrain(), load_hexsides(), engine.types, engine.tables.vehicle)
        assert r30_vehicle_movement.along_road(board, P("B2"), P("C2"))
        assert r30_vehicle_movement.along_road(board, P("B2"), P("C3")) is expected
        facing = next(f for f in range(6) if r28_vehicles.in_covered_arc(P("B2"), f, P("C3")))
        state = engine.new_game(1)
        tank = next(u for u in state.units if u.is_vehicle).with_(hex=P("B2"), facing=facing)
        cost, _, _ = r30_vehicle_movement.entry_cost_halves(ctx, state.with_(units=(tank,)), tank, P("C3"))
        assert cost == (1 if expected else 2)


# ------------------------------------------------------------------ rule 16.1 and PR-53


def test_a_track_hex_out_of_the_defender_s_sight_gives_no_return():
    """Rule 16.1 with PR-53: E5 blocks the line from D5 to F5."""
    case = {
        "phase": "defensive_fire",
        "sub_step": "fire_window",
        "phasing": "russian",
        "units": [
            {"ref": "g", "side": "german", "type": "4-6-7", "hex": "D5"},
            {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "G4", "moved": True, "track": ["F5", "G4"]},
        ],
    }
    cs = build_case(case)
    returns = {p["hex"] for p in of_action(cs, "track_return")}
    assert "F5" not in returns
    assert cs.engine._can_see(cs.state, P("D5"), P("F5")) is False
    case["units"][0]["hex"] = "F7"
    cs = build_case(case)
    assert cs.engine._can_see(cs.state, P("F7"), P("F5"))
    assert "F5" in {p["hex"] for p in of_action(cs, "track_return")}
