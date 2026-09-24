"""TC-34 and TR-09: no opponent-hidden unit leaves the host in the other player's view.

Rule 25.2 says a stack below a concealment counter cannot be inspected by the opposing
player. The view is the only place that can enforce that, so the test plays real games of
scenario 2, which gives each side concealment counters, and reads the view of each player
at each state that has a counter on the board.

The default run plays a few games so that the suite stays fast. The run that TC-34 asks
for plays a hundred games and carries the `gate` marker, so `pytest tests/secrecy -m gate`
is the gate command.
"""

from __future__ import annotations

import pytest

from slagents.base import RandomAgent
from slcore import view
from slcore.engine import Engine
from slcore.game import State
from slcore.rules import r25_concealment
from slcli.play import build_engine
from slhost.server import Host

SCENARIO = "s02_tractor_works"
FAST_GAMES = 2
GATE_GAMES = 100
FAST_COMMANDS = 300
# A game of scenario 2 is about two thousand commands, and a hundred whole games is half
# an hour. The counters go on the board in the Set Up Phase, so the first few hundred
# commands of each game are the part with the most concealment on the board. The gate
# reads that part of a hundred different games.
GATE_COMMANDS = 600


def _payload_ids(payload: dict) -> set[int]:
    """Unit ids named in the host frame: the view, the fire group, the log, and the legal list."""
    found: set[int] = set()
    document = payload["view"]
    for item in document["units"]:
        found.add(item["id"])
    group = document.get("fire_group")
    if group:
        for unit_id, weapon_id in group["members"]:
            found.add(unit_id)
            if weapon_id is not None:
                found.add(weapon_id)
        if group.get("leader") is not None:
            found.add(group["leader"])
    for entry in payload["log_tail"]:
        named: list[int] = []
        view._named_unit_ids(entry.get("data") or {}, named)
        found.update(named)
    for command in payload["legal_commands"]:
        body = command["payload"]
        found.update(int(unit_id) for unit_id in body.get("units", []))
        if body.get("weapon") is not None:
            found.add(int(body["weapon"]))
        if body.get("leader") is not None:
            found.add(int(body["leader"]))
        for unit_id in body.get("targets") or []:
            if isinstance(unit_id, int):
                found.add(unit_id)
    return found


def disclosures(engine: Engine, state: State, viewer: int, payload: dict | None = None) -> list[str]:
    """Everything in the host frame of one player that names a unit that player must not see."""
    hidden = set(view.hidden_unit_ids(state, viewer))
    if not hidden:
        return []
    document = payload["view"] if payload is not None else view.build(state, engine.types, viewer)
    found: list[str] = []
    for item in document["units"]:
        if item["id"] in hidden:
            found.append(f"the view of player {viewer} holds unit {item['id']}")
    for counter in document["concealment"]:
        if not counter["own"] and "units" in counter:
            found.append(f"counter {counter['id']} names the units below it")
    for charge in document["demo"]:
        if not charge["own"]:
            found.append(f"the view of player {viewer} holds the charge {charge['id']} of the other side")
    if payload is None:
        return found
    # A unit that died in view stays in the log. A unit that is still concealed or
    # hidden must not be named by the log, the legal list, or the fire group.
    secret = {u.id for u in state.units if view.secret_from(state, u, viewer)}
    leaked = sorted(_payload_ids(payload) & secret)
    if leaked:
        found.append(f"the frame of player {viewer} names units {leaked}")
    return found


def play_and_watch(engine: Engine, seed: int, max_commands: int) -> tuple[list[str], int, int]:
    """One game. Gives the disclosures, the count of states, and the count with a counter.

    The check reads the frame the host would send to each seat, not only `view.build`.
    """
    host = Host(engine, seed=seed, hot_seat=False)
    host.room.take("c0", "one")
    host.room.take("c1", "two")
    seats = {0: "c0", 1: "c1"}
    state = host.game.state
    agents = (RandomAgent(seed, 0), RandomAgent(seed + 1, 1))
    found: list[str] = []
    states = 0
    concealed = 0
    while not state.game_over and states < max_commands:
        frame = engine.legal_commands(state)
        if not frame.commands:
            break
        states += 1
        if state.concealment:
            concealed += 1
            for viewer in (0, 1):
                payload = host.outbound_frame(seats[viewer], viewer)
                found.extend(disclosures(engine, state, viewer, payload))
        chosen = frame.by_id(agents[frame.player].select(state, frame))
        assert chosen is not None, "an agent selects a command of the frame"
        host.game.apply(frame.frame_id, chosen.id)
        state = host.game.state
    return found, states, concealed


def run_games(count: int, max_commands: int) -> tuple[list[str], int, int]:
    engine = build_engine(SCENARIO)
    found: list[str] = []
    states = 0
    concealed = 0
    for seed in range(1, count + 1):
        game_found, game_states, game_concealed = play_and_watch(engine, seed, max_commands)
        found.extend(game_found)
        states += game_states
        concealed += game_concealed
    return found, states, concealed


def test_a_view_never_names_a_unit_below_an_opposing_counter():
    found, states, concealed = run_games(FAST_GAMES, FAST_COMMANDS)
    assert concealed > 0, "the games must reach a state with concealment counters"
    assert not found, f"{len(found)} disclosures in {states} states: {found[:3]}"


@pytest.mark.gate
def test_one_hundred_games_give_no_disclosure():
    """TC-34: 0 disclosures across 100 games with concealment."""
    found, states, concealed = run_games(GATE_GAMES, GATE_COMMANDS)
    assert concealed > 0
    assert not found, f"{len(found)} disclosures in {states} states: {found[:3]}"


def test_a_player_sees_its_own_stack_below_its_own_counter():
    engine = build_engine(SCENARIO)
    state = engine.new_game(7)
    unit = next(u for u in state.player_units(0) if u.is_infantry)
    state = state.with_unit(unit.with_(hex=(2, 3)))
    state, _ = r25_concealment.add(state, 0, (2, 3))
    own = view.build(state, engine.types, 0)
    other = view.build(state, engine.types, 1)
    assert unit.id in [u["id"] for u in own["units"]], "a player sees its own concealed unit"
    assert unit.id not in [u["id"] for u in other["units"]], "the opponent does not"
    assert own["concealment"][0]["units"] == [unit.id]
    assert "units" not in other["concealment"][0]
    assert other["concealment"][0]["hex"] == "C3"


def test_a_dummy_counter_looks_the_same_as_a_full_stack():
    """Rule 25.7: the opposing player cannot tell a dummy from a stack."""
    engine = build_engine(SCENARIO)
    state = engine.new_game(7)
    unit = next(u for u in state.player_units(0) if u.is_infantry)
    state = state.with_unit(unit.with_(hex=(2, 3)))
    state, _ = r25_concealment.add(state, 0, (2, 3))
    state, _ = r25_concealment.add(state, 0, (4, 5))
    tokens = view.build(state, engine.types, 1)["concealment"]
    full = next(t for t in tokens if t["hex"] == "C3")
    dummy = next(t for t in tokens if t["hex"] == "E5")
    assert set(full) == set(dummy), "the two tokens carry the same fields"
    assert full["stack"] == dummy["stack"] == 1


def test_a_hidden_placement_does_not_reach_the_other_seat():
    """Rule 42.1: the other seat's log does not carry the hex of a hidden placement."""
    engine = build_engine(SCENARIO)
    host = Host(engine, seed=3, hot_seat=False)
    host.room.take("c0", "one")
    host.room.take("c1", "two")
    unit = next(u for u in host.game.state.player_units(0) if u.is_infantry)
    host.game.state = host.game.state.with_unit(unit.with_(hex=(2, 3), hidden=True))
    host.game.log.append({"rule_id": "21.2", "kind": "place", "data": {"unit": unit.id, "hex": "C3"}})
    host.game.log.append({"rule_id": "42.1", "kind": "hidden", "data": {"unit": unit.id, "hex": "C3"}})
    host.game.log.append({"rule_id": "4", "kind": "phase", "data": {"phase": "rally", "turn": 1, "phasing": 0}})
    other = host.outbound_frame("c1", 1)
    blob = str(other["log_tail"])
    assert "C3" not in blob, "the other seat's log names the hidden hex"
    assert unit.id not in _payload_ids(other)
    owner = host.game.log_tail_for(0)
    assert any(entry["kind"] == "hidden" for entry in owner), "the owner still sees the placement"


def test_a_hidden_hex_is_named_but_its_units_are_not():
    """The opponent sees where a counter is. What it hides is what is below it."""
    engine = build_engine(SCENARIO)
    state = engine.new_game(7)
    unit = next(u for u in state.player_units(0) if u.is_infantry)
    state = state.with_unit(unit.with_(hex=(2, 3)))
    state, _ = r25_concealment.add(state, 0, (2, 3))
    assert view.hidden_hex_ids(state, 1) == ("C3",)
    assert unit.id in view.hidden_unit_ids(state, 1), "the concealed unit is hidden from the opponent"
    assert unit.id not in view.hidden_unit_ids(state, 0), "and not from its owner"
    other = next(u for u in state.player_units(0) if u.is_infantry and u.id != unit.id)
    state = state.with_unit(other.with_(hex=(4, 4)))
    assert other.id not in view.hidden_unit_ids(state, 1), "a unit with no counter over it is seen"
