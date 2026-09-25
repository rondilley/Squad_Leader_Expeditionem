"""R1 to R9 of the review of 2026-09-23, with PR-08, PR-36, PR-38 to PR-41.

Each test builds the rule situation with the conformance harness and plays real
commands through the real engine. The dice come from the harness search.
"""

from __future__ import annotations

from slcore import geometry
from slcore.commands import Command
from slcore.game import CcDeclaration
from slcore.rules import r20_close_combat

from conformance.harness import build_case

P = geometry.parse_hex_id


def ids_of(cs) -> list[dict]:
    return [lc.payload for lc in cs.engine.legal_commands(cs.state).commands]


# ---------------------------------------------------------------- R3


def test_two_payload_orders_with_one_id_give_one_hash():
    """R3: the core applies its own copy of the legal command."""
    cs = build_case(
        {
            "phase": "close_combat",
            "sub_step": "cc_declare",
            "actor": "phasing",
            "phasing": "german",
            "melee": ["E7"],
            "units": [
                {"ref": "g1", "side": "german", "type": "4-6-7", "hex": "E7"},
                {"ref": "g2", "side": "german", "type": "4-6-7", "hex": "E7"},
                {"ref": "rs", "side": "russian", "type": "4-4-7", "hex": "E7"},
            ],
        }
    )
    first = Command("cc_attack", units=(cs.ids["g2"], cs.ids["g1"]), extra=(("targets", (cs.ids["rs"],)),))
    second = Command.from_payload(first.payload())
    assert first.id == second.id and first.units != second.units
    one, _ = cs.engine.apply(cs.state, first)
    two, _ = cs.engine.apply(cs.state, second)
    assert cs.engine.hash_state(one) == cs.engine.hash_state(two)


# ---------------------------------------------------------------- R1 and PR-08


def _melee_case(units: list[dict], dice: list[int] | None = None) -> dict:
    case = {
        "phase": "close_combat",
        "sub_step": "cc_declare",
        "actor": "phasing",
        "phasing": "german",
        "melee": ["E7"],
        "units": units,
    }
    if dice:
        case["dice"] = dice
    return case


def test_a_leader_with_no_firepower_declares_no_attack():
    """R1: rules 20.3 and 20.72. A leader stacked with a squad has no close combat firepower."""
    cs = build_case(
        _melee_case(
            [
                {"ref": "gs", "side": "german", "type": "4-6-7", "hex": "E7"},
                {"ref": "gl", "side": "german", "type": "9-2", "hex": "E7"},
                {"ref": "r1", "side": "russian", "type": "4-4-7", "hex": "E7"},
                {"ref": "r2", "side": "russian", "type": "4-4-7", "hex": "E7"},
            ]
        )
    )
    alone = [p for p in ids_of(cs) if p["action"] == "cc_attack" and p["units"] == [cs.ids["gl"]]]
    assert alone == []


def test_an_attack_with_no_firepower_has_no_roll():
    """R1: odds_row gives the row no roll can meet, and resolve rolls no dice for it."""
    cs = build_case(
        _melee_case(
            [
                {"ref": "gs", "side": "german", "type": "4-6-7", "hex": "E7"},
                {"ref": "gl", "side": "german", "type": "9-2", "hex": "E7"},
                {"ref": "r1", "side": "russian", "type": "4-4-7", "hex": "E7"},
            ],
            dice=[1, 1],
        )
    )
    german = cs.engine.scenario.side_index("german")
    state = cs.state.with_(cc_declarations=(CcDeclaration(german, (cs.ids["gl"],), (cs.ids["r1"],)),))
    after, events = r20_close_combat.resolve(state, cs.engine.types, cs.engine.tables.cc)
    assert not after.units[cs.ids["r1"]].eliminated
    assert [e.kind for e in events if e.kind.startswith("cc_")] == ["cc_no_attack"]
    assert after.rng == state.rng, "no die is rolled"
    assert cs.engine.tables.cc.odds_row(0, 4).kill < 2 - 3


def test_three_squads_and_a_leader_may_attack_together():
    """PR-08 with rules 20.4 and 6.1: the whole side of the hex is one attack."""
    cs = build_case(
        _melee_case(
            [
                {"ref": "g1", "side": "german", "type": "4-6-7", "hex": "E7"},
                {"ref": "g2", "side": "german", "type": "4-6-7", "hex": "E7"},
                {"ref": "g3", "side": "german", "type": "4-6-7", "hex": "E7"},
                {"ref": "gl", "side": "german", "type": "9-2", "hex": "E7"},
                {"ref": "r1", "side": "russian", "type": "4-4-7", "hex": "E7"},
            ]
        )
    )
    everyone = sorted(cs.ids[r] for r in ("g1", "g2", "g3", "gl"))
    assert any(p["action"] == "cc_attack" and p["units"] == everyone for p in ids_of(cs))


# ---------------------------------------------------------------- R2 and PR-36


def test_a_broken_unit_that_must_rout_blocks_the_end_of_the_window():
    """R2: rules 13.4 and 13.47. The player cannot decline a mandatory rout."""
    cs = build_case(
        {
            "phase": "advancing_fire",
            "sub_step": "fire_window",
            "phasing": "russian",
            "units": [
                {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "B7", "broken": True},
                {"ref": "g", "side": "german", "type": "4-6-7", "hex": "J10"},
            ],
        }
    )
    cs.state, _ = cs.engine.apply(cs.state, Command("end_phase"))
    assert cs.state.phase == "rout"
    listed = ids_of(cs)
    assert any(p["action"] == "rout" for p in listed)
    assert {"action": "end_phase"} not in listed
    rout = next(p for p in listed if p["action"] == "rout")
    cs.state, _ = cs.engine.apply(cs.state, cs.command(rout))
    assert {"action": "end_phase"} in ids_of(cs)


def test_the_core_looks_again_at_each_broken_unit_at_the_end_of_the_window():
    """PR-36 and rule 13.47: a unit that must rout and has no rout left is eliminated.

    The case starts in the window, so the test of rule 13.47 at the start of the phase has
    not run. Unit b stands next to the enemy with no legal rout, so it has no command.
    Unit a must rout first, and the end of the window then eliminates b.
    """
    cs = build_case(
        {
            "phase": "rout",
            "sub_step": "rout_window",
            "actor": "phasing",
            "phasing": "russian",
            "units": [
                {"ref": "a", "side": "russian", "type": "4-4-7", "hex": "D2", "broken": True},
                {"ref": "b", "side": "russian", "type": "4-4-7", "hex": "A8", "broken": True},
                {"ref": "g", "side": "german", "type": "4-6-7", "hex": "A9"},
            ],
        }
    )
    routs = [p for p in ids_of(cs) if p["action"] == "rout"]
    assert routs and all(p["units"] == [cs.ids["a"]] for p in routs)
    assert {"action": "end_phase"} not in ids_of(cs)
    cs.state, _ = cs.engine.apply(cs.state, cs.command(routs[0]))
    assert {"action": "end_phase"} in ids_of(cs)
    cs.state, events = cs.engine.apply(cs.state, Command("end_phase"))
    assert cs.unit("b").eliminated
    assert any(e.rule_id == "13.47" and e.data.get("unit") == cs.ids["b"] for e in events)


# ---------------------------------------------------------------- R5 and PR-40


def _leader_chain_case() -> dict:
    return {
        "phase": "prep_fire",
        "sub_step": "fire_window",
        "phasing": "russian",
        "units": [
            {"ref": "a", "side": "russian", "type": "4-4-7", "hex": "B7"},
            {"ref": "L", "side": "russian", "type": "9-2", "hex": "B7"},
            {"ref": "b", "side": "russian", "type": "4-4-7", "hex": "B8"},
            {"ref": "t", "side": "german", "type": "4-6-7", "hex": "B10"},
        ],
    }


def _fire_modifiers(cs, sequence: list[dict]) -> list:
    events = []
    for payload in sequence:
        cs.state, ev = cs.engine.apply(cs.state, cs.command(payload))
        events.extend(ev)
    fire = next(e for e in events if e.kind == "fire")
    return [m for m in fire.data["modifiers"] if m["rule"] == "15.2"]


def test_the_leader_modifier_is_zero_when_a_member_hex_has_no_leader_in_either_order():
    """R5: QA-15.2. The sequence of the commands does not change the modifier."""
    leader_first = build_case(_leader_chain_case())
    mods = _fire_modifiers(
        leader_first,
        [
            {"action": "group_add", "units": ["a"], "hex": "B10"},
            {"action": "group_leader", "units": ["L"]},
            {"action": "group_add", "units": ["b"], "hex": "B10"},
            {"action": "group_fire"},
        ],
    )
    assert mods and mods[0]["value"] == 0
    assert not leader_first.unit("L").directed, "a leader with no effect did not direct the fire"
    other = build_case(_leader_chain_case())
    for payload in ({"action": "group_add", "units": ["a"], "hex": "B10"}, {"action": "group_add", "units": ["b"], "hex": "B10"}):
        other.state, _ = other.engine.apply(other.state, other.command(payload))
    assert other.command({"action": "group_leader", "units": ["L"]}).id not in other.engine.legal_commands(other.state).ids()


def test_a_leader_who_mans_a_machine_gun_does_not_direct_other_units():
    """R9 and rule 17.4: the manning leader's rating goes to its own fire only."""
    cs = build_case(
        {
            "phase": "prep_fire",
            "sub_step": "fire_window",
            "phasing": "russian",
            "units": [
                {"ref": "a", "side": "russian", "type": "4-4-7", "hex": "B7"},
                {"ref": "L", "side": "russian", "type": "9-2", "hex": "B7"},
                {"ref": "lmg", "side": "russian", "type": "LMG", "carrier": "L"},
                {"ref": "t", "side": "german", "type": "4-6-7", "hex": "B10"},
            ],
        }
    )
    for payload in ({"action": "group_add", "units": ["a"], "hex": "B10"}, {"action": "group_add_weapon", "units": ["L"], "weapon": "lmg", "hex": "B10"}):
        cs.state, _ = cs.engine.apply(cs.state, cs.command(payload))
    assert cs.command({"action": "group_leader", "units": ["L"]}).id not in cs.engine.legal_commands(cs.state).ids()


# ---------------------------------------------------------------- R6 and PR-41


def test_two_groups_do_not_avoid_the_machine_gun_forfeit():
    """R6: rule 17.2 says 'for that turn'. An MMG and an LMG in two groups cost the inherent fire."""
    cs = build_case(
        {
            "phase": "prep_fire",
            "sub_step": "fire_window",
            "phasing": "russian",
            "units": [
                {"ref": "rs", "side": "russian", "type": "4-4-7", "hex": "B7"},
                {"ref": "lmg", "side": "russian", "type": "LMG", "carrier": "rs"},
                {"ref": "mmg", "side": "russian", "type": "MMG", "carrier": "rs"},
                {"ref": "g1", "side": "german", "type": "4-6-7", "hex": "B9"},
                {"ref": "g2", "side": "german", "type": "4-6-7", "hex": "A9"},
            ],
        }
    )
    for payload in (
        {"action": "group_add", "units": ["rs"], "hex": "B9"},
        {"action": "group_add_weapon", "units": ["rs"], "weapon": "mmg", "hex": "B9"},
        {"action": "group_fire"},
    ):
        cs.state, _ = cs.engine.apply(cs.state, cs.command(payload))
    second = cs.command({"action": "group_add_weapon", "units": ["rs"], "weapon": "lmg", "hex": "A9"})
    assert second.id not in cs.engine.legal_commands(cs.state).ids()


# ---------------------------------------------------------------- R7


def test_a_leader_removed_by_rule_20_71_drops_its_weapon():
    cs = build_case(
        _melee_case(
            [
                {"ref": "gs", "side": "german", "type": "4-6-7", "hex": "E7"},
                {"ref": "rs", "side": "russian", "type": "4-4-7", "hex": "E7"},
                {"ref": "rl", "side": "russian", "type": "8-0", "hex": "E7"},
                {"ref": "lmg", "side": "russian", "type": "LMG", "carrier": "rl"},
            ],
            dice=[1, 1],
        )
    )
    german = cs.engine.scenario.side_index("german")
    state = cs.state.with_(cc_declarations=(CcDeclaration(german, (cs.ids["gs"],), (cs.ids["rs"],)),))
    after, _ = r20_close_combat.resolve(state, cs.engine.types, cs.engine.tables.cc)
    assert after.units[cs.ids["rl"]].eliminated
    weapon = after.units[cs.ids["lmg"]]
    assert weapon.carrier is None and weapon.hex == P("E7") and not weapon.eliminated


# ---------------------------------------------------------------- R8 and PR-38


def _capture_case(weapon: str, army: str = "russian", mover: str = "german", mover_type: str = "4-6-7") -> dict:
    return {
        "phase": "advance",
        "sub_step": "advance_window",
        "phasing": mover,
        "units": [
            {"ref": "gs", "side": mover, "type": mover_type, "hex": "B7"},
            {"ref": "w", "side": army, "type": weapon, "hex": "B7"},
            {"ref": "rs", "side": army, "type": "4-4-7" if army == "russian" else "4-6-7", "hex": "B9"},
        ],
    }


def test_a_captured_machine_gun_changes_owner():
    cs = build_case(_capture_case("LMG"))
    cs.state, events = cs.engine.apply(cs.state, cs.command({"action": "pickup", "units": ["gs"], "weapon": "w"}))
    weapon = cs.unit("w")
    assert weapon.player == cs.unit("gs").player and weapon.carrier == cs.ids["gs"]
    assert any(e.kind == "captured" and e.rule_id == "13.5" for e in events)


def test_a_captured_weapon_that_is_not_a_machine_gun_is_eliminated():
    cs = build_case(_capture_case("DC", army="german", mover="russian", mover_type="4-4-7"))
    cs.state, events = cs.engine.apply(cs.state, cs.command({"action": "pickup", "units": ["gs"], "weapon": "w"}))
    assert cs.unit("w").eliminated
    assert any(e.kind == "captured_eliminated" for e in events)


def test_no_capture_in_a_melee_hex():
    case = _capture_case("LMG")
    case["melee"] = ["B7"]
    case["units"].append({"ref": "rm", "side": "russian", "type": "4-4-7", "hex": "B7"})
    cs = build_case(case)
    assert not any(p["action"] == "pickup" for p in ids_of(cs))


def test_a_captured_broken_weapon_cannot_be_repaired():
    """Rule 18.2: neither side may repair a captured broken support weapon."""
    cs = build_case(
        {
            "phase": "rally",
            "sub_step": "rally_window",
            "actor": "phasing",
            "phasing": "german",
            "units": [
                {"ref": "gs", "side": "german", "type": "4-6-7", "hex": "B7"},
                {"ref": "w", "side": "russian", "type": "LMG", "hex": "B7", "malfunction": True},
                {"ref": "rs", "side": "russian", "type": "4-4-7", "hex": "B9"},
            ],
        }
    )
    captured = cs.state.units[cs.ids["w"]].with_(player=cs.unit("gs").player, carrier=cs.ids["gs"])
    cs.state = cs.state.with_unit(captured)
    assert not any(p["action"] == "repair" for p in ids_of(cs))


# ---------------------------------------------------------------- R9


def test_a_unit_placed_again_takes_its_weapon_along():
    cs = build_case(
        {
            "phase": "setup",
            "sub_step": "place",
            "active": "german",
            "units": [
                {"ref": "gs", "side": "german", "type": "4-6-7", "hex": "A1"},
                {"ref": "lmg", "side": "german", "type": "LMG", "carrier": "gs"},
            ],
        }
    )
    from slcore.rules import r21_setup

    state, _ = r21_setup.apply_place(cs.state, Command("place", units=(cs.ids["gs"],), hex=P("B2")))
    assert state.units[cs.ids["lmg"]].hex == P("B2")


def test_a_previously_broken_leader_that_fails_gives_the_hex_a_second_check():
    """Rule 12.22: a leader, whether previously broken or not, that fails its check."""
    from slcore.rules import r12_morale

    cs = build_case(
        {
            "phase": "prep_fire",
            "sub_step": "fire_window",
            "phasing": "german",
            "dice": [6, 6, 1, 1],
            "units": [
                {"ref": "lead", "side": "russian", "type": "8-0", "hex": "A1", "broken": True},
                {"ref": "s", "side": "russian", "type": "4-4-7", "hex": "A1"},
            ],
        }
    )
    state, events = r12_morale.morale_check(cs.state, cs.engine.types, cs.unit("lead"), 0, "fire")
    assert state.units[cs.ids["lead"]].eliminated
    assert any(e.data.get("cause") == "leader_break" for e in events), [e.to_dict() for e in events]


# ---------------------------------------------------------------- PR-39


def test_the_defender_may_return_one_unit_of_a_track_hex():
    """Rule 16.1: 'any enemy units', so one unit alone is a choice."""
    cs = build_case(
        {
            "phase": "defensive_fire",
            "sub_step": "fire_window",
            "phasing": "russian",
            "units": [
                {"ref": "a", "side": "russian", "type": "4-4-7", "hex": "B3", "moved": True, "track": ["A3", "B3"]},
                {"ref": "b", "side": "russian", "type": "4-4-7", "hex": "B3", "moved": True, "track": ["A3", "B3"]},
                {"ref": "g", "side": "german", "type": "4-6-7", "hex": "A6"},
            ],
        }
    )
    returns = [p for p in ids_of(cs) if p["action"] == "track_return" and p["hex"] == "A3"]
    assert {"action": "track_return", "units": [cs.ids["a"]], "hex": "A3"} in returns
    assert {"action": "track_return", "units": sorted([cs.ids["a"], cs.ids["b"]]), "hex": "A3"} in returns
