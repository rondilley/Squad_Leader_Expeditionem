"""PR-30: a vehicle makes at most one free pivot in a movement phase.

The eval gauntlet found the defect. A pivot inside the hex costs no movement point (rule
30.5 with rule 33.32), so a vehicle could turn to a facing and back again without end, and
the game never terminated. The gauntlet run of v5 against v3 on s04 reached 20000 commands
on two seeds with one vehicle turning between facing 4 and facing 1.

These tests hold the fix. The first plays the two seeds that hung and asserts each game
ends. The second reads the decision frame of a whole game and asserts that the core offers
no pivot to a vehicle that has already pivoted this player turn, which is the invariant that
removes the cycle from the action space (PR-30).
"""

from __future__ import annotations

import pytest

from slcli.play import build_engine, make_agent
from slcore.engine import Engine

SCENARIO = "s04_armor_probe"
# The two seeds that ran past 20000 commands in run 20260912T171618Z-gauntlet-v5.
HUNG_SEEDS = (20260954, 20260962)
CAP = 20000


def _play(engine: Engine, seed: int, cap: int = CAP):
    state = engine.new_game(seed)
    agents = (make_agent("v5", engine, seed, 0), make_agent("v3", engine, seed, 1))
    frames = []
    n = 0
    while not state.game_over and n < cap:
        frame = engine.legal_commands(state)
        assert frame.commands, f"no legal command in {state.phase}/{frame.sub_step} at {n}"
        frames.append((state, frame))
        chosen = frame.by_id(agents[frame.player].select(state, frame))
        assert chosen is not None
        state, _ = engine.apply(state, chosen.command, frame)
        n += 1
    return state, n, frames


@pytest.mark.parametrize("seed", HUNG_SEEDS)
def test_previously_hung_game_terminates(seed: int) -> None:
    engine = build_engine(SCENARIO)
    state, n, _ = _play(engine, seed)
    assert state.game_over, f"seed {seed} still did not end within {CAP} commands"
    assert n < CAP


def test_no_pivot_offered_after_a_vehicle_has_pivoted() -> None:
    """The core offers a pivoted vehicle no further pivot until its movement resets (PR-30)."""
    engine = build_engine(SCENARIO)
    state, n, frames = _play(engine, HUNG_SEEDS[0])
    assert state.game_over
    checked = 0
    for snap, frame in frames:
        for legal in frame.commands:
            if legal.command.action != "vehicle_pivot":
                continue
            vehicle = snap.units[legal.command.units[0]]
            assert not vehicle.pivoted, (
                f"vehicle {vehicle.id} was offered a pivot after it had already pivoted (PR-30)"
            )
            checked += 1
    # The armor game must reach the pivot branch, or this test proves nothing.
    assert checked > 0, "no pivot command appeared in the game; the invariant was not exercised"
