"""The set up tray model (`slwindow.setup`) and the unit text (`slwindow.unitinfo`).

The tests read real frames of the host: the view and the annotated legal list of the
scenario lib01, so the tray shows what a window gets.
"""

from __future__ import annotations

from types import SimpleNamespace

from slcli.play import build_engine
from slcore import view
from slhost import annotate
from slhost.server import Host
from slwindow import setup, unitinfo

SCENARIO = "lib01_grain_office"


def _frame(game, player: int):
    frame = game.engine.legal_commands(game.state)
    legal = annotate.legal_entries(game.engine, game.state, frame, game.names, player, False)
    document = view.build(game.state, game.engine.types, player)
    return SimpleNamespace(phase=frame.phase, legal=legal, view=document, frame=frame)


def _apply(game, snapshot, index: int) -> None:
    game.apply(snapshot.frame.frame_id, snapshot.legal[index]["id"])


def _axis_done(game) -> None:
    for step in range(5):
        snap = _frame(game, 1)
        places = [i for i, e in enumerate(snap.legal) if e["action"] == "place"]
        _apply(game, snap, places[step * 7 % len(places)])
    snap = _frame(game, 1)
    _apply(game, snap, setup.can_finish(snap.legal))


def test_the_tray_shows_each_counter_of_the_side_with_the_ones_to_place_first():
    game = Host(build_engine(SCENARIO), seed=1).game
    snap = _frame(game, 1)
    assert setup.is_setup(snap)
    items = setup.tray(snap.view, snap.legal)
    assert [i.unit_id for i in items] == [13, 10, 11, 12, 14], "the leader, then the squads"
    assert all(not i.placed for i in items)
    assert setup.counts(items) == (0, 5)
    # PR-06 offers the lowest ID of each type, and a click on an identical counter selects it.
    assert setup.offered_id(snap.view, snap.legal, 12) == 10
    assert setup.offered_id(snap.view, snap.legal, 13) == 13
    assert setup.can_finish(snap.legal) is None, "the set up is not complete"


def test_the_targets_are_the_hexes_of_the_legal_list_and_a_placed_counter_is_marked():
    game = Host(build_engine(SCENARIO), seed=1).game
    snap = _frame(game, 1)
    targets = setup.targets(snap.legal, 13)
    named = {e["payload"]["hex"] for e in snap.legal if e["action"] == "place" and e["payload"]["units"] == [13]}
    assert set(targets) == named and named
    hex_id = sorted(targets)[0]
    _apply(game, snap, targets[hex_id][0])
    after = _frame(game, 1)
    item = next(i for i in setup.tray(after.view, after.legal) if i.unit_id == 13)
    assert item.placed and item.hex == hex_id
    assert setup.counts(setup.tray(after.view, after.legal)) == (1, 5)


def test_a_weapon_targets_the_hex_of_a_unit_that_can_carry_it():
    game = Host(build_engine(SCENARIO), seed=1).game
    _axis_done(game)
    snap = _frame(game, 0)
    leader = next(e for e in snap.legal if e["action"] == "place" and e["payload"]["units"] == [0])
    game.apply(snap.frame.frame_id, leader["id"])
    snap = _frame(game, 0)
    weapon = next(u["id"] for u in snap.view["units"] if u.get("own") and u["type"] == "LMG")
    targets = setup.targets(snap.legal, weapon)
    assert leader["payload"]["hex"] in targets
    gifts = [snap.legal[i] for i in targets[leader["payload"]["hex"]]]
    assert any(e["action"] == "place_weapon" for e in gifts)


def test_the_hex_under_the_pointer_where_the_counter_goes_is_marked():
    from slwindow import overlay

    game = Host(build_engine(SCENARIO), seed=1).game
    snap = _frame(game, 1)
    targets = sorted(setup.targets(snap.legal, 13))
    shades = overlay.Tracker().update(snap, 0.0, pinned=13, pointer_hex=targets[0]).shades
    assert shades[targets[0]] == overlay.TONE_DROP
    assert all(shades[h] == overlay.TONE_SETUP for h in targets[1:])
    # A hex where the counter cannot go gets no mark.
    other = next(f"A{row}" for row in range(1, 40) if f"A{row}" not in targets)
    assert overlay.Tracker().update(snap, 0.0, pinned=13, pointer_hex=other).shades.get(other) is None


def test_no_tray_outside_the_set_up():
    game = Host(build_engine(SCENARIO), seed=1).game
    snap = _frame(game, 1)
    assert not setup.is_setup(SimpleNamespace(phase="rally", legal=snap.legal))
    assert not setup.is_setup(SimpleNamespace(phase="setup", legal=[]))


def test_the_unit_text_names_each_value_of_the_counter():
    game = Host(build_engine(SCENARIO), seed=1).game
    units = {u["id"]: u for u in view.build(game.state, game.engine.types, 0)["units"]}
    squad = units[3]
    assert unitinfo.title(squad) == "Russian 6-2-8 squad"
    lines = unitinfo.facts(squad)
    assert "Firepower 6: the strength of its fire attack." in lines
    assert "Normal range 2 hexes." in lines
    assert "Morale 8: it passes a morale check on this number or less." in lines
    assert "Elite unit." in lines
    assert "Not on the board yet." in lines
    leader = unitinfo.facts(units[0])
    assert "Leadership -3: it adds this to the dice of the units it directs." in leader
    weapon = unitinfo.facts(units[7])
    assert weapon[0] == "A machine gun. A squad or a leader carries it and fires it."
    assert "Breakdown 10: it malfunctions on a fire roll of this number or more." in weapon


def _place_first(game, unit_id: int, hex_id: str | None = None) -> str:
    snap = _frame(game, 0)
    entries = [e for e in snap.legal if e["action"] == "place" and e["payload"]["units"] == [unit_id]]
    entry = next(e for e in entries if hex_id is None or e["payload"]["hex"] == hex_id)
    game.apply(snap.frame.frame_id, entry["id"])
    return entry["payload"]["hex"]


def test_a_machine_gun_waits_for_the_units_and_then_goes_only_onto_a_unit_that_carries_it():
    game = Host(build_engine(SCENARIO), seed=1).game
    _axis_done(game)
    snap = _frame(game, 0)
    # No unit is on the board: the weapon has no target, and the tray says why.
    assert setup.weapon_step(snap.view, snap.legal, 8) == setup.WEAPON_WAIT
    assert setup.targets(snap.legal, 8, snap.view) == {}
    item = next(i for i in setup.tray(snap.view, snap.legal) if i.unit_id == 8)
    assert setup.item_label(snap.view, snap.legal, item) == "units first"
    assert "Place your squads and leaders first" in setup.hint(snap.view, snap.legal, 8)
    leader_hex = _place_first(game, 0)
    squad_hex = _place_first(game, 3, next(h for h in setup.targets(_frame(game, 0).legal, 3) if h != leader_hex))
    snap = _frame(game, 0)
    # A leader cannot carry the MMG, so the one target is the hex of the squad, and a
    # unit is still to place, so a hex alone is not a target.
    targets = setup.targets(snap.legal, 8, snap.view)
    assert set(targets) == {squad_hex}
    assert [snap.legal[i]["action"] for i in targets[squad_hex]] == ["place_weapon"]
    assert "Drag the MMG onto a shaded unit" in setup.hint(snap.view, snap.legal, 8)
    game.apply(snap.frame.frame_id, snap.legal[targets[squad_hex][0]]["id"])
    snap = _frame(game, 0)
    item = next(i for i in setup.tray(snap.view, snap.legal) if i.unit_id == 8)
    assert setup.item_label(snap.view, snap.legal, item) == "with 6-2-8"
    # The host gives the owner the movement of the carrier: 4 factors less 1 for the
    # portage of 4 above the free 3 (rule 5.7), and 2 more in a stack with a leader.
    squad = next(u for u in snap.view["units"] if u["id"] == 3)
    assert squad["carries"] == [8]
    assert (squad["movement_halves"], squad["movement_free_halves"], squad["movement_stack_halves"]) == (6, 8, 10)
    lines = unitinfo.facts(squad, snap.view)
    assert "Carries the MMG. They move with it." in lines
    assert "Movement factors 3 with this load (4 with no load). 5 when it moves in a stack with a leader." in lines
    weapon = next(u for u in snap.view["units"] if u["id"] == 8)
    weapon_lines = unitinfo.facts(weapon, snap.view)
    assert "A machine gun. A squad carries it and fires it. A leader cannot carry it." in weapon_lines
    assert any(line.startswith("Portage 4 for a squad:") for line in weapon_lines)
    assert "Carried by the 6-2-8. It moves with that unit, and the 6-2-8 fires it." in weapon_lines
    # The other side does not get the movement of the carrier (AR-09).
    other = next(u for u in view.build(game.state, game.engine.types, 1)["units"] if u["id"] == 3)
    assert "movement_halves" not in other


def test_the_board_draws_a_carried_weapon_directly_after_its_carrier():
    from slwindow.overlay import units_in, with_carried

    view_doc = {
        "units": [
            {"id": 3, "kind": "squad", "hex": "C4", "carrier": None},
            {"id": 0, "kind": "leader", "hex": "C4", "carrier": None},
            {"id": 8, "kind": "sw", "hex": "C4", "carrier": 3},
        ]
    }
    stack = units_in(view_doc, "C4")
    assert [u["id"] for u in stack] == [0, 3], "a click never puts the weapon in focus"
    assert [u["id"] for u in with_carried(stack, view_doc)] == [0, 3, 8]


def test_a_move_label_names_the_weapon_that_goes_with_the_unit():
    game = Host(build_engine(SCENARIO), seed=1).game
    _axis_done(game)
    _place_first(game, 3)
    snap = _frame(game, 0)
    gift = next(e for e in snap.legal if e["action"] == "place_weapon" and e["payload"]["weapon"] == 8)
    game.apply(snap.frame.frame_id, gift["id"])

    def name(uid: int) -> str:
        return game.names.for_viewer(game.state, uid, 0)

    assert annotate._with_weapons(game.state, 3, name) == f"{name(3)} (with {name(8)})"
    assert annotate._with_weapons(game.state, 4, name) == name(4)
