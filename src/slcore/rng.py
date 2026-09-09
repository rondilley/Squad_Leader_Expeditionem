"""xoshiro128** with a 32-bit state, the one random generator of the core (FR-11).

Reference: David Blackman and Sebastiano Vigna, xoshiro128** 1.1, CC0. The
port keeps each word at 32 bits with a mask. The seed expands through
splitmix64 into four words, as the reference recommends.
"""

from __future__ import annotations

MASK32 = 0xFFFFFFFF
MASK64 = 0xFFFFFFFFFFFFFFFF

RngState = tuple[int, int, int, int]


def _rotl32(x: int, k: int) -> int:
    return ((x << k) | (x >> (32 - k))) & MASK32


def splitmix64(seed: int) -> tuple[int, int]:
    """One splitmix64 step: the next state and the output."""
    seed = (seed + 0x9E3779B97F4A7C15) & MASK64
    z = seed
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
    z = z ^ (z >> 31)
    return seed, z


def seed_state(seed: int) -> RngState:
    """Four 32-bit words from a 64-bit seed. A zero state is not possible."""
    s = seed & MASK64
    words: list[int] = []
    while len(words) < 4:
        s, out = splitmix64(s)
        words.append(out & MASK32)
        words.append((out >> 32) & MASK32)
    state = (words[0], words[1], words[2], words[3])
    if state == (0, 0, 0, 0):
        state = (1, 2, 3, 4)
    return state


def next_u32(state: RngState) -> tuple[RngState, int]:
    """One xoshiro128** step. Gives the new state and a 32-bit output."""
    s0, s1, s2, s3 = state
    result = (_rotl32((s1 * 5) & MASK32, 7) * 9) & MASK32
    t = (s1 << 9) & MASK32
    s2 ^= s0
    s3 ^= s1
    s1 ^= s2
    s0 ^= s3
    s2 ^= t
    s3 = _rotl32(s3, 11)
    return (s0, s1, s2, s3), result


def roll_die(state: RngState) -> tuple[RngState, int]:
    """One six-sided die, 1 to 6, without modulo bias."""
    limit = (1 << 32) - ((1 << 32) % 6)
    while True:
        state, value = next_u32(state)
        if value < limit:
            return state, value % 6 + 1


def roll_2d6(state: RngState) -> tuple[RngState, tuple[int, int]]:
    """Two dice, in sequence. The pair is kept so that the log shows each die."""
    state, a = roll_die(state)
    state, b = roll_die(state)
    return state, (a, b)


def choice_index(state: RngState, count: int) -> tuple[RngState, int]:
    """A uniform index in range(count), without modulo bias."""
    if count <= 0:
        raise ValueError("count must be positive")
    limit = (1 << 32) - ((1 << 32) % count)
    while True:
        state, value = next_u32(state)
        if value < limit:
            return state, value % count
