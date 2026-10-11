"""The action log the host sends a player names no unit that player could not see (AR-09).

Before this test the host sent the same log to each seat, and the log named the placement
of a hidden unit (rule 42.1) and the moves of a concealed unit (rule 25.2). The check here
does not use the filter it tests: while the game plays, it records each unit that is ever
in the view of player 0, and no unit ID in the log of player 0 may be outside that record.
The test also shows that the whole log of the host names units that player 0 never saw, so
the scenario does test the filter.
"""

from __future__ import annotations

import pytest

from slcli.play import build_engine, make_agent
from slcore import view
from slhost.logview import named_units
from slhost.server import Host

PERSON = 0


def _seen(host: Host) -> set[int]:
    return {u["id"] for u in view.build(host.game.state, host.engine.types, PERSON)["units"]}


def _ids(entries) -> set[int]:
    out: set[int] = set()
    for entry in entries:
        out |= named_units(entry.get("data") or {})
    out.discard(None)
    return out


def _play(scenario: str, agent: str, seed: int, limit: int = 4000):
    """Play a game one command at a time, and give for each command the units player 0
    saw just before and just after it, the new entries of player 0's log, and the new
    entries of the whole log."""
    engine = build_engine(scenario)
    host = Host(engine, seed=seed, agents={1: make_agent(agent, engine, seed, 1)})
    agents = {PERSON: make_agent(agent, engine, seed + 1, PERSON), 1: host.agents[1]}
    own = {u.id for u in host.game.state.units if u.player == PERSON}
    steps = []
    while not host.game.state.game_over and len(steps) < limit:
        state = host.game.state
        before = _seen(host)
        mine = len(host.game.player_logs.get(PERSON, []))
        whole = len(host.game.log)
        frame = engine.legal_commands(state)
        host.game.apply(frame.frame_id, agents[state.active].select(state, frame))
        allowed = before | _seen(host) | own
        steps.append((allowed, host.game.player_logs[PERSON][mine:], host.game.log[whole:]))
    return host, steps


@pytest.mark.parametrize(
    "scenario,agent,seed",
    [("s00c_two_board_advance", "v1", 3), ("s02_tractor_works", "v2", 4), ("s01_guards_counterattack", "v1", 5)],
)
def test_the_log_of_a_player_names_only_units_that_player_saw(scenario, agent, seed):
    host, steps = _play(scenario, agent, seed)
    hidden_events = 0
    for number, (allowed, mine, whole) in enumerate(steps, start=1):
        leaked = _ids(mine) - allowed
        assert not leaked, f"command {number}: the log of player {PERSON} names units it did not see: {sorted(leaked)}"
        if _ids(whole) - allowed:
            hidden_events += 1
    # The whole log named units player 0 did not see, so the filter had work to do.
    assert hidden_events > 0, "the scenario hid no unit from player 0"


def test_a_fire_into_a_hidden_unit_keeps_its_result_and_drops_the_unit_id():
    """The firer reads the result of a fire, with the unit made unknown, and not nothing."""
    host, steps = _play("s02_tractor_works", "v2", 4)
    redacted = 0
    hidden_results = 0
    for allowed, mine, whole in steps:
        hidden_results += sum(
            1 for e in whole if e["kind"] == "fire_result" and set(e["data"].get("units") or []) - allowed
        )
        redacted += sum(1 for e in mine if e["kind"] == "fire_result" and None in (e["data"].get("units") or []))
    assert hidden_results > 0, "no fire went into a unit player 0 did not see"
    assert redacted == hidden_results
