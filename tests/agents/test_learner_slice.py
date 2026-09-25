"""The learned observation, the option head, the seeded sample, and the snapshot load.

A hidden unit and a concealed unit are absent from the other player's planes and rows.
Two support weapons at one hex stay two commands. `choose` repeats from one generator
seed. A file that is not a weight file does not load.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("torch")
pytest.importorskip("gymnasium")
pytest.importorskip("pettingzoo")

import torch

from conformance.harness import build_case
from slagents.learned import encoding, imitate, ppo
from slagents.learned.agent import load_policy
from slagents.learned.env import make_env
from slagents.learned.league import write_snapshot
from slagents.learned.nets import NetConfig, Policy
from slagents.learned.reward import term_counts
from slcli.play import build_engine
from slcore.events import Event


class _Marker:
    """A plain object. It is not a weight file."""


def test_a_hidden_unit_and_a_concealed_unit_are_absent_from_the_other_player():
    """The other player sees neither squad, and a dummy pays the same sneak term as the stack."""
    built = build_case(
        {
            "phase": "prep_fire",
            "sub_step": "fire_window",
            "phasing": "german",
            "active": "german",
            "units": [
                {"ref": "own", "side": "german", "type": "4-6-7", "hex": "A1"},
                {"ref": "hid", "side": "russian", "type": "4-4-7", "hex": "C3", "hidden": True},
                {"ref": "con", "side": "russian", "type": "4-4-7", "hex": "A4"},
            ],
            "concealment": [{"side": "russian", "hex": "A4"}],
        }
    )
    engine = built.engine
    state = built.state
    viewer = engine.scenario.side_index("german")
    spaces = encoding.spaces_for(engine.board, len(state.units))
    planes = encoding.board_tensor(engine.board, state, engine.types, viewer, spaces, _building())
    rows = encoding.unit_tensor(state, engine.types, viewer, spaces, engine.board)
    unit_base = len(encoding.TERRAIN_KINDS) + 4
    theirs = unit_base + 6 + 4 + 3
    for ref in ("C3", "A4"):
        col, row = _hex(ref)
        assert planes[unit_base + 3, col, row] == 0.0
        assert planes[unit_base + 4, col, row] == 0.0
        assert planes[unit_base + 5, col, row] == 0.0
    assert rows[built.ids["hid"] + 1].sum() == 0.0
    assert rows[built.ids["con"] + 1].sum() == 0.0
    assert rows[built.ids["own"] + 1][0] == 1.0
    col, row = _hex("C3")
    assert planes[theirs, col, row] == 0.0, "a hidden enemy does not give the building to the other side"

    shown = state.with_unit(replace(built.unit("hid"), hidden=False)).with_(concealment=())
    shown_planes = encoding.board_tensor(engine.board, shown, engine.types, viewer, spaces, _building())
    assert shown_planes[unit_base + 3, col, row] > 0.0
    assert shown_planes[theirs, col, row] == 1.0

    mover = built.unit("own")
    # The sneak term pays at the end of the Movement Phase, for a unit with a track (L1).
    moving = state.with_(phase="movement", phasing=mover.player).with_unit(replace(mover, track=((0, 0),)))
    event = Event("4", "phase", {"phase": "defensive_fire", "turn": 1, "phasing": mover.player})
    full = state.with_unit(replace(built.unit("hid"), eliminated=True))
    dummy = full.with_unit(replace(built.unit("con"), eliminated=True, hex=None))
    visible = state.with_(concealment=()).with_unit(replace(built.unit("hid"), eliminated=True))
    full_counts = term_counts(engine, moving, full, [event])
    dummy_counts = term_counts(engine, moving, dummy, [event])
    visible_counts = term_counts(engine, moving, visible, [event])
    side = mover.player
    assert full_counts[side]["sneak"] == dummy_counts[side]["sneak"] == 1
    assert visible_counts[side]["sneak"] == 0


def test_two_weapons_at_one_hex_stay_two_commands_and_the_teacher_keeps_the_second():
    """Option 0 is the lower command id. The teacher label of the other weapon is not that command."""
    built = build_case(
        {
            "phase": "prep_fire",
            "sub_step": "fire_window",
            "phasing": "german",
            "active": "german",
            "units": [
                {"ref": "s", "side": "german", "type": "4-6-7", "hex": "A1"},
                {"ref": "w1", "side": "german", "type": "LMG", "carrier": "s"},
                {"ref": "w2", "side": "german", "type": "LMG", "carrier": "s"},
                {"ref": "e", "side": "russian", "type": "4-4-7", "hex": "A3"},
            ],
        }
    )
    frame = built.engine.legal_commands(built.state)
    groups = encoding.group_commands(frame, encoding.hex_slots(built.engine.board))
    adds = [item for item in groups.values() if item.command.action == "group_add_weapon"]
    assert len(adds) == 2
    keys = [key for key, item in groups.items() if item.command.action == "group_add_weapon"]
    assert len({key[:3] for key in keys}) == 1
    assert {key[3] for key in keys} == {0, 1}
    ordered = sorted(adds, key=lambda item: item.id)
    prefix = keys[0][:3]
    assert groups[(*prefix, 0)].id == ordered[0].id
    assert groups[(*prefix, 1)].command.weapon != groups[(*prefix, 0)].command.weapon

    class Teacher:
        def select(self, state, decision):
            return ordered[1].id

    class Stub:
        def __init__(self):
            self.state_ = built.state
            self.frame = frame
            self.groups = groups

    key = imitate._teacher_key(Teacher(), Stub())
    assert key[3] == 1
    assert groups[key].command.weapon == ordered[1].command.weapon
    assert groups[key].id != groups[(*prefix, 0)].id


def test_choose_repeats_from_one_generator_seed():
    """The same generator seed gives the same command, including the option."""
    torch.manual_seed(0)
    engine = build_engine("s01_guards_counterattack")
    env = make_env(engine, seed=9)
    policy = Policy(env.spaces_record, NetConfig(channels=4, board_width=32, unit_width=16, hidden=32))
    observation = env.observe(env.agent_selection)
    first = ppo.choose(policy, observation, env, torch.Generator().manual_seed(11))
    second = ppo.choose(policy, observation, env, torch.Generator().manual_seed(11))
    assert first[0] == second[0]
    assert len(first[0]) == 4


def test_a_file_that_is_not_weights_does_not_load(tmp_path: Path):
    """The load path rejects a pickle that is not a weight file. The file is built here."""
    path = tmp_path / "marker.pt"
    torch.save(_Marker(), path)
    with pytest.raises(Exception):
        load_policy(path)


def test_the_snapshot_extra_must_be_json(tmp_path: Path):
    """A snapshot extra that is not JSON does not go into the file."""
    engine = build_engine("s01_guards_counterattack")
    env = make_env(engine, seed=1)
    policy = Policy(env.spaces_record, NetConfig(channels=4, board_width=32, unit_width=16, hidden=32))
    with pytest.raises(ValueError):
        write_snapshot(policy, tmp_path / "bad.pt", 0, policy.config, extra={"bad": object()})


def _hex(name: str) -> tuple[int, int]:
    from slcore import geometry

    return geometry.parse_hex_id(name)


def _building() -> encoding.Objectives:
    hexes = tuple(_hex(name) for name in ("C3", "C4", "C5", "B5"))
    return encoding.Objectives((("B1", hexes),), ())
