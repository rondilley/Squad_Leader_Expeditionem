"""Rule 42, Hidden Initial Placement (FR-10).

Concealment says where a unit is not. Hidden placement says nothing at all: the unit is on
the owner's record and on no board that the other player sees. So the tests here check two
things at once, the rule and the secrecy of the view (AR-09).
"""

from __future__ import annotations

import collections

import pytest

from slcore import view
from slcore.rules import r42_hidden
from slcli.play import build_engine, make_agent, play_game

SCENARIO = "s00c_two_board_advance"


@pytest.fixture(scope="module")
def engine():
    return build_engine(SCENARIO)


@pytest.fixture(scope="module")
def played(engine):
    return play_game(engine, 5, (make_agent("v2", engine, 5, 0), make_agent("v1", engine, 5, 1)))


def kinds(record) -> collections.Counter:
    return collections.Counter((e["rule_id"], e["kind"]) for e in record.events)


# ------------------------------------------------------------------ 42.1, the record


def test_the_scenario_names_the_side_that_may_hide(engine):
    assert engine.scenario.hidden_side == "defender"


def test_a_scenario_with_no_hidden_side_hides_nothing():
    other = build_engine("s01_guards_counterattack")
    assert other.scenario.hidden_side == ""
    record = play_game(other, 3, (make_agent("v1", other, 3, 0), make_agent("v1", other, 3, 1)))
    assert kinds(record)[("42.1", "hidden")] == 0


def test_the_named_side_hides_units_at_set_up(played):
    assert kinds(played)[("42.1", "hidden")] > 0


def test_only_a_woods_hex_or_a_building_hex_holds_a_hidden_unit(engine, played):
    """Rule 42.1 names the two terrain types."""
    board = engine.board
    for event in played.events:
        if (event["rule_id"], event["kind"]) != ("42.1", "hidden"):
            continue
        ref = board.by_id(event["data"]["hex"]).ref
        assert r42_hidden.hex_allows_hiding(board, ref)


def test_the_hiding_terrain_is_woods_and_the_two_buildings():
    assert set(r42_hidden.HIDING_KINDS) == {"woods", "stone_building", "wooden_building"}


def test_a_unit_of_the_other_side_never_hides(engine, played):
    ids = {e["data"]["unit"] for e in played.events if (e["rule_id"], e["kind"]) == ("42.1", "hidden")}
    state = engine.new_game(5)
    defender = engine.scenario.side_index("defender")
    for unit_id in ids:
        assert state.units[unit_id].player == defender


# --------------------------------------------------------------- 42.2, the reveal


def test_a_hidden_unit_comes_on_the_board(played):
    assert kinds(played)[("42.2", "revealed")] > 0


def test_each_hidden_unit_is_on_the_board_by_the_end(engine, played):
    """Rule 42.2 has four causes, and a game of six turns reaches one of them."""
    hidden = sum(1 for e in played.events if (e["rule_id"], e["kind"]) == ("42.1", "hidden"))
    shown = sum(
        1
        for e in played.events
        if e["kind"] == "revealed" and e["rule_id"] in ("42.2", "42.4")
    )
    assert shown == hidden


def test_a_reveal_says_why_it_happened(played):
    causes = {
        e["data"]["cause"]
        for e in played.events
        if e["kind"] == "revealed" and e["rule_id"].startswith("42")
    }
    assert causes
    known = {
        r42_hidden.CAUSE_MOVED,
        r42_hidden.CAUSE_FIRED,
        r42_hidden.CAUSE_SMOKE,
        r42_hidden.CAUSE_ADJACENT,
        r42_hidden.CAUSE_HIT,
        "the unit placed a charge",
    }
    assert causes <= known, causes


def test_a_unit_that_came_on_the_board_does_not_go_back(engine, played):
    """Rule 42.3."""
    order = []
    for event in played.events:
        key = (event["rule_id"], event["kind"])
        if key == ("42.1", "hidden"):
            order.append(("hide", event["data"]["unit"]))
        elif event["kind"] == "revealed" and event["rule_id"].startswith("42"):
            order.append(("show", event["data"]["unit"]))
    seen: set[int] = set()
    for what, unit_id in order:
        if what == "show":
            seen.add(unit_id)
        else:
            assert unit_id not in seen, "a unit that came on the board went back"


# -------------------------------------------------------------------- the secrecy


def test_the_view_of_the_other_player_holds_no_hidden_unit(engine):
    """AR-09 and TR-09: the view names the units the viewer may know about."""
    state = engine.new_game(5)
    for _ in range(400):
        frame = engine.legal_commands(state)
        if not frame.commands:
            break
        agents = {p: make_agent("v1", engine, 5, p) for p in (0, 1)}
        chosen = frame.by_id(agents[frame.player].select(state, frame))
        state, _ = engine.apply(state, chosen.command, frame)
        hidden = r42_hidden.hidden_units(state)
        if not hidden:
            continue
        for unit in hidden:
            other = 1 - unit.player
            document = view.build(state, engine.types, other)
            assert unit.id not in {u["id"] for u in document["units"]}
            assert not view.visible_to(state, unit, other)
            assert view.hidden_from(state, unit, other)
        break
    else:
        pytest.fail("no hidden unit appeared in the first four hundred commands")


def test_the_owner_sees_its_own_hidden_unit(engine):
    state = engine.new_game(5)
    for _ in range(400):
        frame = engine.legal_commands(state)
        if not frame.commands:
            break
        agents = {p: make_agent("v1", engine, 5, p) for p in (0, 1)}
        chosen = frame.by_id(agents[frame.player].select(state, frame))
        state, _ = engine.apply(state, chosen.command, frame)
        hidden = r42_hidden.hidden_units(state)
        if hidden:
            unit = hidden[0]
            document = view.build(state, engine.types, unit.player)
            assert unit.id in {u["id"] for u in document["units"]}
            return
    pytest.fail("no hidden unit appeared in the first four hundred commands")


# ------------------------------------------------------- 42.4 and 42.5, the mechanics


def test_a_hidden_unit_takes_fire_at_half_strength(engine):
    """Rule 42.4 with rule 9.4."""
    state = engine.new_game(5)
    assert r42_hidden.halves_for(state, (0, 1), 8) == 8, "no hidden unit, so no halving"


def test_the_halving_reads_the_hex(engine):
    state = engine.new_game(5)
    changed = {}
    unit = next(u for u in state.units if u.kind == "squad")
    changed[unit.id] = unit.with_(hex=(4, 4), hidden=True)
    state = state.with_units(changed)
    assert r42_hidden.halves_for(state, (4, 4), 8) == 4
    assert r42_hidden.halves_for(state, (5, 4), 8) == 8


def test_a_hidden_unit_does_not_make_a_hex_illegal_to_enter(engine):
    """Rule 42.5: the mover does not know, so the move is legal and then it stops."""
    from slcore.rules.r05_movement import enemy_in_hex

    state = engine.new_game(5)
    unit = next(u for u in state.units if u.kind == "squad")
    state = state.with_unit(unit.with_(hex=(4, 4), hidden=True))
    assert not enemy_in_hex(state, 1 - unit.player, (4, 4))
    state = state.with_unit(state.units[unit.id].with_(hidden=False))
    assert enemy_in_hex(state, 1 - unit.player, (4, 4))


def test_the_hidden_units_of_a_hex_are_the_ones_in_it(engine):
    state = engine.new_game(5)
    unit = next(u for u in state.units if u.kind == "squad")
    state = state.with_unit(unit.with_(hex=(6, 6), hidden=True))
    assert [u.id for u in r42_hidden.hidden_in(state, (6, 6))] == [unit.id]
    assert r42_hidden.hidden_in(state, (7, 6)) == ()
    assert r42_hidden.enemy_hidden_in(state, (6, 6), 1 - unit.player)
    assert not r42_hidden.enemy_hidden_in(state, (6, 6), unit.player)


# ------------------------------------------------------------- what waits for a tier


def test_blind_fire_names_the_tier_it_waits_for(engine):
    """The first half of rule 42.4 changes the action space, so it has its own tier."""
    with pytest.raises(r42_hidden.HiddenNotAvailable) as exc:
        r42_hidden.blind_fire_hexes(engine.board, (0, 1))
    assert "42.4" in str(exc.value)
    assert "FR-50" in str(exc.value)


# ------------------------------------------------------------------- determinism


def test_a_game_with_hidden_units_replays(engine):
    first = play_game(engine, 9, (make_agent("v1", engine, 9, 0), make_agent("v1", engine, 9, 1)))
    second = play_game(engine, 9, (make_agent("v1", engine, 9, 0), make_agent("v1", engine, 9, 1)))
    assert first.hashes == second.hashes


def test_the_hidden_flag_is_in_the_state_hash(engine):
    """A replay that does not reproduce the hash sequence is a defect, so the flag counts."""
    state = engine.new_game(5)
    unit = next(u for u in state.units if u.kind == "squad")
    before = engine.hash_state(state)
    after = engine.hash_state(state.with_unit(unit.with_(hidden=True)))
    assert before != after
