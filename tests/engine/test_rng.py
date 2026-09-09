import json
from pathlib import Path

from slcore.rng import choice_index, next_u32, roll_2d6, roll_die, seed_state

GOLDEN = Path(__file__).parent / "golden_xoshiro128ss.json"


def test_golden_vector_from_the_javascript_port():
    doc = json.loads(GOLDEN.read_text(encoding="utf-8"))
    state = tuple(doc["seed_state"])
    out = []
    for _ in range(len(doc["outputs"])):
        state, v = next_u32(state)
        out.append(v)
    assert out == doc["outputs"]
    assert len(out) == 1000


def test_seed_state_is_deterministic_and_never_zero():
    assert seed_state(42) == seed_state(42)
    assert seed_state(42) != seed_state(43)
    assert seed_state(0) != (0, 0, 0, 0)
    for word in seed_state(2**64 - 1):
        assert 0 <= word < 2**32


def test_dice_range_and_reproducibility():
    state = seed_state(7)
    rolls = []
    for _ in range(600):
        state, d = roll_die(state)
        rolls.append(d)
    assert set(rolls) == {1, 2, 3, 4, 5, 6}
    state2 = seed_state(7)
    again = []
    for _ in range(600):
        state2, d = roll_die(state2)
        again.append(d)
    assert rolls == again
    state, pair = roll_2d6(seed_state(9))
    assert all(1 <= d <= 6 for d in pair)


def test_choice_index_covers_range():
    state = seed_state(3)
    seen = set()
    for _ in range(500):
        state, i = choice_index(state, 7)
        seen.add(i)
    assert seen == set(range(7))
