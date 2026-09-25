"""SR-09 at the core: the legal list and the view of a seat never name a secret unit.

Each test plays real random games with the real engine. After each command it reads,
for each seat, the legal list the seat would get (the list of the frame when the seat
acts, and nothing when it does not) and `view.build` for that seat. Neither may name a
unit that `view.visible_to` hides from that seat.

The second property is the one rule 25.7 asks for: the legal list does not change when
the units below an opposing concealment counter, or an opposing hidden unit, are taken
off the board. So a dummy and a real stack give the same list, and a hidden unit gives
the list of an empty hex.
"""

from __future__ import annotations

from typing import Any

import pytest

from slagents.base import RandomAgent
from slcli.play import build_engine
from slcore import view
from slcore.engine import Engine
from slcore.game import State

# Scenarios 2 and 3A carry concealment and sewers, scenario 4 the armour, scenario 0B
# concealment with three armies, and scenario 0C the hidden initial placement of rule 42.
SCENARIOS = ("s02_tractor_works", "s03a_streets_of_stalingrad", "s04_armor_probe", "s00b_combined_forces", "s00c_two_board_advance")
FAST_SEEDS = (1, 2)
FAST_COMMANDS = 700
GATE_SEEDS = tuple(range(1, 21))
GATE_COMMANDS = 3000
# The swap check builds a second frame, so it runs on each fourth state that needs it.
SWAP_EVERY = 4

UNIT_KEYS = ("weapon", "leader", "vehicle")
UNIT_LIST_KEYS = ("units", "targets")


def named_in_payload(payload: dict[str, Any]) -> set[int]:
    found: set[int] = set()
    for key in UNIT_LIST_KEYS:
        for item in payload.get(key) or []:
            if isinstance(item, int):
                found.add(item)
    for key in UNIT_KEYS:
        if isinstance(payload.get(key), int):
            found.add(payload[key])
    return found


def named_in_view(document: dict[str, Any]) -> set[int]:
    found = {item["id"] for item in document["units"]}
    group = document.get("fire_group")
    if group:
        for unit_id, weapon_id in group["members"]:
            found.add(unit_id)
            if weapon_id is not None:
                found.add(weapon_id)
        if group.get("leader") is not None:
            found.add(group["leader"])
    for counter in document["concealment"]:
        found.update(counter.get("units", []))
    return found


def secret_ids(state: State, seat: int) -> set[int]:
    return {u.id for u in state.units if u.player != seat and not u.eliminated and not view.visible_to(state, u, seat)}


def leaks(engine: Engine, state: State, frame, seat: int) -> list[str]:
    secret = secret_ids(state, seat)
    if not secret:
        return []
    out: list[str] = []
    if frame.player == seat:
        for lc in frame.commands:
            named = named_in_payload(lc.payload) & secret
            if named:
                out.append(f"seat {seat} legal command {lc.payload} names {sorted(named)} in {state.phase}")
    named = named_in_view(view.build(state, engine.types, seat)) & secret
    if named:
        out.append(f"the view of seat {seat} names {sorted(named)} in {state.phase}")
    return out


def without_secrets(state: State, seat: int) -> State | None:
    """The state with each unit that the seat cannot see taken off the board.

    A counter keeps its place, so a real stack becomes a dummy. The weapons of those
    units go with them. None when nothing is secret from the seat.
    """
    secret = secret_ids(state, seat)
    if not secret:
        return None
    changed = {uid: state.units[uid].with_(hex=None, carrier=None) for uid in secret}
    return state.with_units(changed)


def swap_differences(engine: Engine, state: State, frame) -> list[str]:
    swapped = without_secrets(state, frame.player)
    if swapped is None:
        return []
    other = engine.legal_commands(swapped)
    got = [lc.payload for lc in frame.commands]
    want = [lc.payload for lc in other.commands]
    if got == want:
        return []
    only_real = [p for p in got if p not in want]
    only_swap = [p for p in want if p not in got]
    return [f"seat {frame.player} in {state.phase}/{frame.sub_step}: the list depends on secret units: real only {only_real[:3]}, swapped only {only_swap[:3]}"]


def play(engine: Engine, seed: int, max_commands: int) -> tuple[list[str], int, int]:
    state = engine.new_game(seed)
    agents = (RandomAgent(seed, 0), RandomAgent(seed + 1, 1))
    found: list[str] = []
    secret_states = 0
    swapped = 0
    for step in range(max_commands):
        if state.game_over:
            break
        frame = engine.legal_commands(state)
        assert frame.commands, f"no legal command in {state.phase}/{frame.sub_step}"
        for seat in (0, 1):
            found.extend(leaks(engine, state, frame, seat))
        if secret_ids(state, frame.player):
            secret_states += 1
            if secret_states % SWAP_EVERY == 0:
                swapped += 1
                found.extend(swap_differences(engine, state, frame))
        chosen = frame.by_id(agents[frame.player].select(state, frame))
        state, _ = engine.apply(state, chosen.command, frame)
    return found, secret_states, swapped


def run(scenario: str, seeds: tuple[int, ...], max_commands: int) -> None:
    engine = build_engine(scenario)
    found: list[str] = []
    secret_states = 0
    swapped = 0
    for seed in seeds:
        game_found, game_secret, game_swapped = play(engine, seed, max_commands)
        found.extend(game_found)
        secret_states += game_secret
        swapped += game_swapped
    assert not found, f"{len(found)} disclosures in {scenario}: {found[:3]}"
    # Scenario 4 has concealment counters since the review of 2026-09-23, so each scenario
    # here reaches a state with a secret unit.
    assert secret_states > 0, f"the games of {scenario} reach no state with a secret unit"
    assert swapped > 0


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_no_seat_sees_a_secret_unit_in_its_list_or_its_view(scenario):
    run(scenario, FAST_SEEDS, FAST_COMMANDS)


@pytest.mark.gate
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_twenty_games_of_each_scenario_give_no_disclosure(scenario):
    run(scenario, GATE_SEEDS, GATE_COMMANDS)
