"""L7: the gate command plays its games in the seed range of its own family."""

from __future__ import annotations

from slcli.gates import run_gate
from slruns.seeds import FAMILY_BASE, family_seed


def test_the_gate_plays_in_its_own_seed_range():
    assert "gate" in FAMILY_BASE
    bases = sorted(FAMILY_BASE.values())
    assert len(bases) == len(set(bases)), "each family has a range of its own"
    art = run_gate("s00_movement_drill", None, "v1", "v0", 2, 1, shuffle_games=0)
    assert art.seeds == [family_seed("gate", 1, 0), family_seed("gate", 1, 1)]
    assert art.config["seed_family"] == "gate" and art.config["first_seed"] == 1
    for other in ("train", "gauntlet", "evolve", "tournament"):
        assert family_seed(other, 1, 0) not in art.seeds
