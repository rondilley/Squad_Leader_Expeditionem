"""The engineer tools of rules 22, 23, and 27 in agents v4 to v7 (`slagents.scripted.engineer`).

Each test plays a real game of a real scenario:
- The set up gives each flamethrower and each charge to an assault engineer squad, and
  it spreads the load. Before this, one 8-3-8 squad of scenario 2 held all eight weapons
  of its group and did not move in the whole game.
- v7 fires a flamethrower, places a charge, and explodes it in scenario 2, and it takes a
  sewer in scenario 3A. Before this it took none of them.
- `v7[engineer=false]` takes none of them, so the measure compares the two records.
- Each decision is a legal command, and a game of the new v7 replays to the same hash.
"""

from __future__ import annotations

from collections import Counter

import pytest

from slagents.base import decide
from slagents.registry import build_engine, make_agent
from slcore.game import PHASE_SETUP
from slcore.rules import r22_flamethrower, r23_demolition

TOOLS = ("ft_fire", "place_demo", "explode_demo", "sewer_move", "sewer_return")


def _play(scenario: str, names: tuple[str, str], seed: int, until_setup_ends: bool = False):
    """The final state, the count of the tools each side took, and the hashes of the game."""
    engine = build_engine(scenario)
    agents = [make_agent(name, engine, seed, player) for player, name in enumerate(names)]
    state = engine.new_game(seed)
    used: Counter = Counter()
    hashes = []
    while not state.game_over:
        frame = engine.legal_commands(state)
        if until_setup_ends and frame.phase != PHASE_SETUP:
            break
        choice = decide(agents[frame.player], state, frame)
        legal = frame.by_id(choice)
        assert legal is not None, f"{names[frame.player]} gave a command that is not in the frame"
        if legal.command.action in TOOLS:
            used[legal.command.action] += 1
        state, _ = engine.apply(state, legal.command, frame)
        hashes.append(engine.hash_state(state))
    return engine, state, used, hashes


@pytest.mark.parametrize("agent", ["v4", "v6", "v7"])
def test_the_set_up_gives_each_engineer_weapon_to_an_engineer_and_spreads_the_load(agent):
    engine, state, _, _ = _play("s02_tractor_works", (agent, agent), seed=1, until_setup_ends=True)
    types = engine.types
    load: Counter = Counter()
    for weapon in state.units:
        special = r22_flamethrower.is_flamethrower(types, weapon) or r23_demolition.is_charge(types, weapon)
        if not special or weapon.carrier is None:
            continue
        carrier = state.units[weapon.carrier]
        assert types[carrier.type_key].assault_engineer, f"{weapon.type_key} went to {carrier.type_key}"
        load[carrier.id] += 1
    # Six engineer squads for two flamethrowers and four charges: no squad needs two.
    assert load and max(load.values()) == 1


@pytest.mark.slow
def test_v7_uses_the_flamethrower_and_the_charge_in_scenario_2():
    used: Counter = Counter()
    for seed in (1, 2, 3, 4):
        _, _, counts, _ = _play("s02_tractor_works", ("v7", "v7"), seed)
        used += counts
    assert used["ft_fire"] >= 1
    assert used["place_demo"] >= 1
    assert used["explode_demo"] >= 1


@pytest.mark.slow
def test_v7_takes_a_sewer_in_scenario_3a():
    used: Counter = Counter()
    for seed in (1, 2, 3):
        _, _, counts, _ = _play("s03a_streets_of_stalingrad", ("v7", "v7"), seed)
        used += counts
    assert used["sewer_move"] >= 1


@pytest.mark.slow
def test_the_switch_off_record_takes_no_engineer_tool():
    off = "v7[engineer=false]"
    _, _, used, _ = _play("s02_tractor_works", (off, off), seed=1)
    assert sum(used[t] for t in ("ft_fire", "place_demo", "sewer_move")) == 0


@pytest.mark.slow
def test_a_game_of_the_engineer_v7_replays_to_the_same_hashes():
    _, first, _, hashes_a = _play("s02_tractor_works", ("v7", "v7"), seed=2)
    _, second, _, hashes_b = _play("s02_tractor_works", ("v7", "v7"), seed=2)
    assert hashes_a == hashes_b
    assert first.result == second.result


# ------------------------------------------------ the tool value of the v7 move (2026-09-25)


def _carrier_case(enemy_hex: str | None, counter: bool = False, name: str = "v7[tool_weight=2]"):
    """A German 8-3-8 with a charge in C2, three hexes from F2, in its Movement Phase.

    The tool value is off in the v7 record (it lost on the measure of 2026-09-25), so
    the case turns it on by name.
    """
    from conformance.harness import build_case
    from slcore.player_state import for_player

    units = [
        {"ref": "e", "side": "german", "type": "8-3-8", "hex": "C2"},
        {"ref": "dc", "side": "german", "type": "DC", "carrier": "e"},
        # A Russian squad far away, so the order of battle has a squad type in view.
        {"ref": "far", "side": "russian", "type": "4-4-7", "hex": "A9"},
    ]
    if enemy_hex is not None:
        units.append({"ref": "t", "side": "russian", "type": "4-4-7", "hex": enemy_hex})
    case = {"phase": "movement", "phasing": "german", "active": "german", "units": units}
    if counter:
        case["concealment"] = [{"side": "russian", "hex": "F2"}]
    built = build_case(case)
    player = built.unit("e").player
    agent = make_agent(name, built.engine, 1, player)
    view = for_player(built.state, player)
    agent._refresh_routes(view)
    agent._refresh_objectives(view)
    return agent, view, view.units[built.unit("e").id]


def _points(agent, view, unit, hex_id: str) -> int:
    from slcore import geometry

    hex_ref = geometry.parse_hex_id(hex_id)
    return agent._tool_points(view, unit, hex_ref, hex_ref != unit.hex)


def test_a_step_that_reaches_a_charge_hex_carries_the_charge_and_a_stand_away_does_not():
    agent, view, unit = _carrier_case("F2")
    assert _points(agent, view, unit, "C2") == 0  # the stand, three hexes away
    assert _points(agent, view, unit, "D2") > 0  # two hexes away, and F2 is in reach
    assert _points(agent, view, unit, "E2") > 0  # next to F2
    off, off_view, off_unit = _carrier_case("F2", name="v7")
    assert all(_points(off, off_view, off_unit, h) == 0 for h in ("C2", "D2", "E2"))


def test_a_counter_over_a_squad_and_a_dummy_counter_give_the_same_tool_value():
    """S4: the agent does not read what is below a concealment counter."""
    real = _carrier_case("F2", counter=True)
    dummy = _carrier_case(None, counter=True)
    for hex_id in ("D2", "E2"):
        assert _points(*real, hex_id) == _points(*dummy, hex_id) > 0
    # The counter halves the charge (rule 23.5), so a squad in view is worth more.
    seen = _carrier_case("F2")
    assert _points(*seen, "E2") > _points(*real, "E2")
