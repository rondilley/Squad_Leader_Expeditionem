"""From the draws of a random scenario to a `Scenario` the engine can play (FR-17).

`generator.draw_scenario` says what the scenario is: the board type, the two armies, the
turn count, the victory condition, and the two forces. This module lays those out on a
board and gives back a `Scenario`.

The layout follows rules 11 and 12 of the printed method. The defender sets up first and
the attacker moves first. The two sides start in bands of columns at the two ends of the
board, with a gap between them, so that no attacker starts next to a defender.

The defender always has two groups. One holds a stone building, because the building
victory conditions of rule 6 name a building of the defender. The other holds the ground
around it. The attacker has one group in its own band. Each group stays inside the limits
of rule 6.1, and the module divides the force until it does.
"""

from __future__ import annotations

from typing import Mapping

from slboards import edges
from slboards.generator import GeneratorParameters, ZoneConstraint
from slcampaign.generator import Draw, Force, ScenarioError
from slcore.rules import r06_stacking
from slcore.scenario import Group, Scenario, SetupArea, SideSpec, UnitEntry, VictoryCondition
from slcore.units import KIND_LEADER, KIND_SW, UnitType

ATTACKER = "attacker"
DEFENDER = "defender"
DEFENDER_BAND = (20, 32)
ATTACKER_BAND = (0, 8)
BOARD_RETRIES = 24
BUILDING_MIN_HEXES = 2
BUILDING_MAX_HEXES = 6


def entries(counts, types: Mapping[str, UnitType], kinds) -> list[UnitEntry]:
    """The unit entries of one kind group, with the type key the engine wants."""
    out = []
    for key, count in counts:
        if types[key].kind in kinds or (kinds == "squads" and types[key].is_squad_like):
            out.append(UnitEntry(key.split(":", 1)[1], count, ""))
    return out


def split_force(force: Force, types: Mapping[str, UnitType]) -> tuple[list[UnitEntry], list[UnitEntry]]:
    """The force in two parts: the holding group and the rest.

    The holding group takes the leader, up to three squads, and up to two weapons, which
    is what a building of two hexes holds under rule 6.1. The rest is the second group.
    """
    hold: list[UnitEntry] = []
    rest: list[UnitEntry] = []
    squads_held = 0
    weapons_held = 0
    for key, count in force.counts:
        name = key.split(":", 1)[1]
        unit_type = types[key]
        if unit_type.kind == KIND_LEADER:
            hold.append(UnitEntry(name, count, ""))
            continue
        if unit_type.is_squad_like:
            take = min(count, max(0, r06_stacking.LIMIT_SQUADS - squads_held))
            squads_held += take
        elif unit_type.kind == KIND_SW:
            take = min(count, max(0, 2 - weapons_held))
            weapons_held += take
        else:
            take = 0
        if take:
            hold.append(UnitEntry(name, take, ""))
        if count - take:
            rest.append(UnitEntry(name, count - take, ""))
    if not hold:
        raise ScenarioError("a force with no leader and no squad cannot hold a building")
    return hold, rest


OPEN_GROUND = ("stone_building", "wooden_building")


def band_area(low: int, high: int, buildings: bool = True) -> SetupArea:
    """A band of columns. Without buildings, the band leaves them to the holding group."""
    params = [("min_col", low), ("max_col", high)]
    if not buildings:
        params.append(("not_terrain", OPEN_GROUND))
    return SetupArea(zone="columns", params=tuple(sorted(params)))


def building_area(low: int, high: int, rank: int) -> SetupArea:
    return SetupArea(
        zone="stone_building",
        params=(("min_col", low), ("max_col", high), ("rank", rank), ("min_hexes", BUILDING_MIN_HEXES)),
    )


def victory_for(draw: Draw) -> tuple[VictoryCondition, ...]:
    """The condition of rule 6 that the draw chose, as a record the core evaluates.

    The side is always the attacker. The printed method writes each condition as a task
    for the attacker, and the defender wins when the attacker does not finish it.
    """
    kind = draw.victory_kind
    if kind == "sole_occupant":
        return (VictoryCondition(kind, (("groups", ("d_hold",)), ("side", ATTACKER))),)
    if kind == "building_count":
        return (VictoryCondition(kind, (("count", 1), ("groups", ("d_hold",)), ("side", ATTACKER))),)
    if kind == "force_eliminated":
        return (VictoryCondition(kind, (("side", ATTACKER),)),)
    if kind == "casualty_exchange":
        return (VictoryCondition(kind, (("margin", 1), ("side", ATTACKER))),)
    if kind == "unbroken_squad_ratio":
        return (
            VictoryCondition(kind, (("denominator", 1), ("numerator", 1), ("side", ATTACKER))),
        )
    raise ScenarioError(f"the victory condition {kind!r} has no layout in this build")


def build_scenario(
    seed: int,
    draw: Draw,
    defending: Force,
    attacking: Force,
    types: Mapping[str, UnitType],
    name: str | None = None,
) -> Scenario:
    """The scenario record. The board comes from the generator when the loader reads it."""
    hold, rest = split_force(defending, types)
    zones = (
        ZoneConstraint(
            count=2,
            min_hexes=BUILDING_MIN_HEXES,
            max_hexes=BUILDING_MAX_HEXES,
            min_col=DEFENDER_BAND[0],
            max_col=DEFENDER_BAND[1],
        ),
    )
    generator = GeneratorParameters(
        seed=seed,
        board_type=draw.board_type,
        cols=edges.COLS,
        rows=edges.ROWS,
        zones=zones,
    )
    defender_groups = [
        Group("d_hold", tuple(hold), building_area(*DEFENDER_BAND, 0), objective=True),
    ]
    if rest:
        defender_groups.append(Group("d_line", tuple(rest), band_area(*DEFENDER_BAND, buildings=False)))
    attacker_groups = [
        Group(
            "a_force",
            tuple(entries(attacking.counts, types, "squads") + entries(attacking.counts, types, (KIND_LEADER, KIND_SW))),
            band_area(*ATTACKER_BAND),
            objective=True,
        )
    ]
    scenario_id = name or f"random-{seed}"
    return Scenario(
        id=scenario_id,
        title=f"Random scenario {seed}: {draw.attacker} attacks {draw.defender} on a {draw.board_type} board",
        board=draw.board_type,
        turns=draw.turns,
        first_mover=ATTACKER,
        setup_order=(DEFENDER, ATTACKER),
        sides=(
            SideSpec(ATTACKER, draw.attacker, tuple(attacker_groups)),
            SideSpec(DEFENDER, draw.defender, tuple(defender_groups)),
        ),
        rules_used=tuple(str(n) for n in range(1, 27)),
        switches=(("predesignation", "basic"), ("semi_simultaneous", "off")),
        victory=victory_for(draw),
        board_generator=tuple(sorted(generator.to_dict().items(), key=lambda kv: kv[0])),
        board_retries=BOARD_RETRIES,
        notes=(
            f"Built by the random scenario construction of Game Set IV from seed {seed}. "
            f"The victory condition is: {draw.victory_text}. "
            f"The defending force is {draw.defender_points} points and the attacking force is "
            f"{draw.attacker_points} points, a share of {draw.attack_share[0]} to {draw.attack_share[1]}."
        ),
    )
