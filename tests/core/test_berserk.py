"""R4 and PR-37: the berserk charge of rules 18.4 to 18.43.

A berserk unit charges the nearest enemy unit in its line of sight by the shortest route
in movement factors, in its Movement Phase and its Advance Phase, and attacks it in close
combat. It has 6 movement factors as a squad and 8 as a leader. It does not fire in the
Prep Fire Phase, and rule 18.41 keeps it immune to morale checks.
"""

from __future__ import annotations

from slcore import geometry
from slcore.commands import Command
from slcore.rules import r05_movement, r12_morale

from conformance.harness import build_case

P = geometry.parse_hex_id


def payloads(cs) -> list[dict]:
    return [lc.payload for lc in cs.engine.legal_commands(cs.state).commands]


def _movement_case(extra_units: list[dict] | None = None) -> dict:
    units = [
        {"ref": "b", "side": "russian", "type": "4-4-7", "hex": "A3", "berserk": True},
        {"ref": "g", "side": "german", "type": "4-6-7", "hex": "A8"},
    ]
    return {
        "phase": "movement",
        "sub_step": "move_window",
        "phasing": "russian",
        "units": units + (extra_units or []),
    }


def test_the_charge_is_the_only_command_while_it_has_a_step():
    cs = build_case(_movement_case([{"ref": "other", "side": "russian", "type": "4-4-7", "hex": "C2"}]))
    listed = payloads(cs)
    assert listed, "the charge has a step"
    assert all(p["action"] == "move" and p["units"] == [cs.ids["b"]] for p in listed), listed
    assert {"action": "move", "units": [cs.ids["b"]], "hex": "A4"} in listed


def test_the_charge_goes_to_the_enemy_and_stops_next_to_it():
    cs = build_case(_movement_case())
    for _ in range(10):
        listed = payloads(cs)
        if {"action": "end_phase"} in listed:
            break
        cs.state, _ = cs.engine.apply(cs.state, cs.command(listed[0]))
    here = cs.unit("b").hex
    assert geometry.distance(here, P("A8")) == 1, f"the unit stops next to its target, at {geometry.hex_id(*here)}"
    assert {"action": "end_phase"} in payloads(cs)


def test_a_berserk_squad_has_six_movement_factors_and_a_leader_eight():
    cs = build_case(
        _movement_case(
            [
                {"ref": "L", "side": "russian", "type": "8-1", "hex": "C2", "berserk": True},
            ]
        )
    )
    ctx = cs.engine.move_ctx
    assert r05_movement.allowance_halves(ctx, cs.state, cs.unit("b"), leader_bonus=False) == 12
    assert r05_movement.allowance_halves(ctx, cs.state, cs.unit("L"), leader_bonus=False) == 16
    assert r05_movement.allowance_halves(ctx, cs.state, cs.unit("b"), leader_bonus=True) == 16


def test_with_no_enemy_in_sight_the_unit_moves_as_it_likes():
    cs = build_case(
        {
            "phase": "movement",
            "sub_step": "move_window",
            "phasing": "russian",
            "units": [
                {"ref": "b", "side": "russian", "type": "4-4-7", "hex": "A3", "berserk": True},
                {"ref": "g", "side": "german", "type": "4-6-7", "hex": "D5"},
            ],
        }
    )
    assert not cs.engine._sees_fn(cs.state)(P("A3"), P("D5")), "the stone building of C4 blocks the line"
    listed = payloads(cs)
    assert {"action": "end_phase"} in listed
    assert {"action": "move", "units": [cs.ids["b"]], "hex": "A2"} in listed, "a move away from the enemy is free"


def test_the_charge_advances_into_the_enemy_hex():
    cs = build_case(
        {
            "phase": "advance",
            "sub_step": "advance_window",
            "phasing": "russian",
            "units": [
                {"ref": "b", "side": "russian", "type": "4-4-7", "hex": "A7", "berserk": True},
                {"ref": "g", "side": "german", "type": "4-6-7", "hex": "A8"},
                {"ref": "other", "side": "russian", "type": "4-4-7", "hex": "C2"},
            ],
        }
    )
    listed = payloads(cs)
    assert listed == [{"action": "advance", "units": [cs.ids["b"]], "hex": "A8"}]
    cs.state, _ = cs.engine.apply(cs.state, cs.command(listed[0]))
    assert {"action": "end_phase"} in payloads(cs)


def test_a_berserk_unit_in_a_melee_hex_must_attack():
    cs = build_case(
        {
            "phase": "close_combat",
            "sub_step": "cc_declare",
            "actor": "phasing",
            "phasing": "russian",
            "units": [
                {"ref": "b", "side": "russian", "type": "4-4-7", "hex": "A8", "berserk": True},
                {"ref": "g", "side": "german", "type": "4-6-7", "hex": "A8"},
            ],
        }
    )
    listed = payloads(cs)
    assert {"action": "end_phase"} not in listed
    attack = next(p for p in listed if p["action"] == "cc_attack")
    cs.state, _ = cs.engine.apply(cs.state, cs.command(attack))
    assert {"action": "end_phase"} in payloads(cs)


def test_a_berserk_unit_does_not_fire_in_the_prep_fire_phase():
    cs = build_case(
        {
            "phase": "prep_fire",
            "sub_step": "fire_window",
            "phasing": "russian",
            "units": [
                {"ref": "b", "side": "russian", "type": "4-4-7", "hex": "A7", "berserk": True},
                {"ref": "g", "side": "german", "type": "4-6-7", "hex": "A8"},
            ],
        }
    )
    assert payloads(cs) == [{"action": "end_phase"}]


def test_a_berserk_unit_fires_in_the_defensive_fire_phase():
    cs = build_case(
        {
            "phase": "defensive_fire",
            "sub_step": "fire_window",
            "phasing": "german",
            "units": [
                {"ref": "b", "side": "russian", "type": "4-4-7", "hex": "A7", "berserk": True},
                {"ref": "g", "side": "german", "type": "4-6-7", "hex": "A8"},
            ],
        }
    )
    assert {"action": "group_add", "units": [cs.ids["b"]], "hex": "A8"} in payloads(cs)


def test_a_broken_unit_that_rolls_two_becomes_berserk_and_is_not_broken():
    """Rule 18.4: 'even if already broken'."""
    cs = build_case(
        {
            "phase": "prep_fire",
            "sub_step": "fire_window",
            "phasing": "german",
            "dice": [1, 1],
            "units": [{"ref": "b", "side": "russian", "type": "4-4-7", "hex": "A7", "broken": True}],
        }
    )
    state, events = r12_morale.morale_check(cs.state, cs.engine.types, cs.unit("b"), 2, "fire")
    unit = state.units[cs.ids["b"]]
    assert unit.berserk and not unit.broken
    assert events[0].rule_id == "18.4"


def test_a_berserk_unit_takes_no_morale_check():
    """Rule 18.41: immune to all morale checks for the rest of the scenario."""
    cs = build_case(
        {
            "phase": "prep_fire",
            "sub_step": "fire_window",
            "phasing": "german",
            "dice": [6, 6],
            "units": [{"ref": "b", "side": "russian", "type": "4-4-7", "hex": "A7", "berserk": True}],
        }
    )
    state, events = r12_morale.morale_check(cs.state, cs.engine.types, cs.unit("b"), 4, "fire")
    assert events == [] and state == cs.state


def test_a_berserk_unit_picks_up_only_what_costs_it_no_factor():
    """Rule 18.43 and QA-18.42: a squad carries three portage points at most."""
    cs = build_case(
        {
            "phase": "movement",
            "sub_step": "move_window",
            "phasing": "russian",
            "units": [
                {"ref": "b", "side": "russian", "type": "4-4-7", "hex": "A3", "berserk": True},
                {"ref": "mmg", "side": "russian", "type": "MMG", "hex": "A3"},
            ],
        }
    )
    assert not r05_movement.pickup_allowed(cs.engine.move_ctx, cs.state, cs.unit("b"), cs.unit("mmg"), True)
    assert Command("pickup", units=(cs.ids["b"],), weapon=cs.ids["mmg"]).id not in cs.engine.legal_commands(cs.state).ids()
