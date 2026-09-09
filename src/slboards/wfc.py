"""The fill pass: Wave Function Collapse over the hexes that pass 2 left open.

Each hex holds a domain of tile kinds. The solver takes the hex with the smallest
domain, selects one kind by weight from the seeded generator, and propagates the
adjacency rule to the neighbors. When a domain empties, the solver reports it, and the
caller tries the next seed. The board is small, so a bounded number of tries is enough.

Source: docs/research/2026-09-07_RV-7_browser_engine.md section 6.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from slboards.tiles import Tile, allowed
from slcore import geometry
from slcore.geometry import HexRef
from slcore.rng import RngState, choice_index

MAX_TRIES = 12


class FillFailed(Exception):
    """No assignment satisfies the adjacency rules from this seed."""


@dataclass
class Wave:
    domains: dict[HexRef, set[str]]
    fixed: dict[HexRef, str]

    def settled(self) -> bool:
        return all(len(d) == 1 for d in self.domains.values())

    def result(self) -> dict[HexRef, str]:
        out = dict(self.fixed)
        for ref, domain in self.domains.items():
            out[ref] = next(iter(domain))
        return out


def neighbors_on(board_hexes: Iterable[HexRef], ref: HexRef) -> list[HexRef]:
    present = set(board_hexes)
    return [n for n in geometry.neighbors(*ref) if n in present]


def collapse(
    rng: RngState,
    free: list[HexRef],
    fixed: Mapping[HexRef, str],
    tiles: Mapping[str, Tile],
    kinds: tuple[str, ...],
) -> tuple[RngState, dict[HexRef, str]]:
    """Fill the free hexes. Raises FillFailed when a domain empties."""
    all_refs = list(free) + list(fixed)
    wave = Wave({ref: set(kinds) for ref in free}, dict(fixed))
    seed_domains(wave, tiles, all_refs)
    while not wave.settled():
        ref = smallest_domain(wave)
        if ref is None:
            break
        options = sorted(wave.domains[ref])
        rng, chosen = weighted_choice(rng, options, tiles)
        wave.domains[ref] = {chosen}
        propagate(wave, tiles, all_refs, ref)
    return rng, wave.result()


def smallest_domain(wave: Wave) -> HexRef | None:
    best: HexRef | None = None
    best_size = 1 << 30
    for ref in sorted(wave.domains):
        size = len(wave.domains[ref])
        if 1 < size < best_size:
            best_size = size
            best = ref
    return best


def weighted_choice(rng: RngState, options: list[str], tiles: Mapping[str, Tile]) -> tuple[RngState, str]:
    total = sum(max(1, tiles[k].weight) for k in options)
    rng, roll = choice_index(rng, total)
    running = 0
    for kind in options:
        running += max(1, tiles[kind].weight)
        if roll < running:
            return rng, kind
    return rng, options[-1]


def seed_domains(wave: Wave, tiles: Mapping[str, Tile], all_refs: list[HexRef]) -> None:
    """Reduce each domain by the hexes that pass 2 fixed."""
    for ref in list(wave.fixed):
        _reduce_neighbors(wave, tiles, all_refs, ref, wave.fixed[ref])


def propagate(wave: Wave, tiles: Mapping[str, Tile], all_refs: list[HexRef], start: HexRef) -> None:
    stack = [start]
    while stack:
        ref = stack.pop()
        kinds = wave.domains.get(ref)
        current = wave.fixed.get(ref) if kinds is None else None
        options = {current} if current is not None else set(kinds or ())
        for neighbor in neighbors_on(all_refs, ref):
            domain = wave.domains.get(neighbor)
            if domain is None:
                continue
            keep = {k for k in domain if any(allowed(tiles, k, option) for option in options)}
            if not keep:
                raise FillFailed(f"the domain of {geometry.hex_id(*neighbor)} is empty")
            if keep != domain:
                wave.domains[neighbor] = keep
                stack.append(neighbor)


def _reduce_neighbors(wave: Wave, tiles: Mapping[str, Tile], all_refs: list[HexRef], ref: HexRef, kind: str) -> None:
    for neighbor in neighbors_on(all_refs, ref):
        domain = wave.domains.get(neighbor)
        if domain is None:
            continue
        keep = {k for k in domain if allowed(tiles, k, kind)}
        if not keep:
            raise FillFailed(f"the domain of {geometry.hex_id(*neighbor)} is empty next to {kind}")
        wave.domains[neighbor] = keep
