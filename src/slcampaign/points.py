"""The force point scale (FR-17, Game Set IV).

The design-your-own rules build a force against a point total, and the printed Point Value
Chart gives a number for each counter. That chart is a graphic on page 34 of the rulebook,
so a search of the text layer finds nothing. A read of the page as an image finds it, which
is how the armor tables of rule 33 reached `sldata/tables/armor.json`. Open item O-08 is
the same work for this chart.

Until someone does it, this module holds the project's own scale. It is not the 1977 chart,
and it does not claim to be. It reads the values that are already in the counter data and gives a
number that ranks the counters the way the chart ranks them: an elite squad above a line
squad, a leader above a squad, and a heavy machine gun above a light one.

The scale:

- A squad or a crew is `firepower * 4 + range * 2 + morale * 3`, and an elite unit gets a
  quarter more, because rule 2.6 gives it the higher morale and the better recovery.
- A leader is `morale * 3 + leadership * 12`, where leadership is the size of the modifier.
  A leader with no modifier is still worth its morale, because rule 14.1 says a broken
  squad rallies only with a leader in the hex.
- A support weapon is `firepower * 2 + range`, and a weapon that breaks on a low number
  loses a tenth for each step below twelve, because rule 18.1 takes it out of the game. A
  weapon that leaves the game when it fires is halved: rule 23.4 removes the demolition
  charge after it explodes, so its thirty firepower factors arrive one time only, and rule
  37.3 removes the panzerfaust in the same way. A weapon whose target is armour has no
  infantry firepower on its counter, so its value is its reach times five.
- A vehicle is `gun_score + mp * 3 + machine guns * 4`, where the gun score is the
  firepower the hit is worth on the Infantry Fire Table (rule 34.2) times six. A gun that
  fires high explosive only loses a fifth, because rule 33.6 keeps it off the armour
  piercing columns of the kill table. A gun with an asterisk loses a fifth again, because
  rule 33.31 cases B and C make it miss at range. An open top vehicle loses a fifth,
  because rule 46.54 and rule 34.8 let infantry fire into it. A turret adds a quarter,
  because rule 33.31 case D charges a self-propelled gun much more to shoot to the side.

Each number is an integer, because a point total is a count and not a measurement.
"""

from __future__ import annotations

from typing import Mapping

from slcore.units import CLASS_TANK, KIND_LEADER, KIND_SW, KIND_VEHICLE, UnitType

ELITE_NUMERATOR = 5
ELITE_DENOMINATOR = 4
BREAKDOWN_BEST = 12
# Rule 23.4 removes the charge after it explodes and rule 37.3 removes the panzerfaust,
# so each of them fires one time in a game.
ONE_SHOT = ("demo", "panzerfaust")
# Rules 37.3 and 37.4: a weapon whose target is armour has no infantry firepower of its
# own, so its reach against a vehicle is what it is worth.
ANTI_TANK_WEIGHT = 5

# Rule 34.2: the firepower a hit from each calibre is worth on the Infantry Fire Table.
# The scale reads the same numbers the armor table holds, so a point value does not need
# the table itself and the core stays out of the file system.
GUN_FIREPOWER = ((150, 30), (120, 20), (100, 16), (80, 12), (70, 8), (50, 6), (40, 4), (30, 2), (20, 1))
GUN_WEIGHT = 6
MOVEMENT_WEIGHT = 3
MACHINE_GUN_WEIGHT = 4
FIFTH_NUMERATOR = 4
FIFTH_DENOMINATOR = 5


def gun_score(unit_type: UnitType) -> int:
    """Rule 34.2: what the main gun is worth, from the calibre rounded down."""
    for calibre, firepower in GUN_FIREPOWER:
        if unit_type.gun >= calibre:
            return firepower * GUN_WEIGHT
    return 0


def vehicle_points(unit_type: UnitType) -> int:
    """Rules 28 to 41: the point value of one vehicle counter on the project's own scale."""
    base = (
        gun_score(unit_type)
        + unit_type.mp * MOVEMENT_WEIGHT
        + (unit_type.mg_ca + unit_type.mg_360) * MACHINE_GUN_WEIGHT
    )
    if unit_type.gun_he_only:
        base = base * FIFTH_NUMERATOR // FIFTH_DENOMINATOR
    if unit_type.gun_low_velocity:
        base = base * FIFTH_NUMERATOR // FIFTH_DENOMINATOR
    if unit_type.open_top:
        base = base * FIFTH_NUMERATOR // FIFTH_DENOMINATOR
    if unit_type.vehicle_class == CLASS_TANK:
        base = base * ELITE_NUMERATOR // ELITE_DENOMINATOR
    return max(1, base)


def unit_points(unit_type: UnitType) -> int:
    """The point value of one counter on the project's own scale."""
    if unit_type.kind == KIND_VEHICLE:
        return vehicle_points(unit_type)
    if unit_type.kind == KIND_LEADER:
        return unit_type.morale * 3 + abs(unit_type.leadership) * 12
    if unit_type.kind == KIND_SW:
        if unit_type.firepower:
            base = unit_type.firepower * 2 + unit_type.range
        else:
            base = unit_type.range * ANTI_TANK_WEIGHT
        if unit_type.weapon_class in ONE_SHOT:
            base //= 2
        # A breakdown number of zero means the weapon does not break, so it takes no cut.
        steps = max(0, BREAKDOWN_BEST - unit_type.breakdown) if unit_type.breakdown else 0
        return max(1, base - base * steps // 10)
    base = unit_type.firepower * 4 + unit_type.range * 2 + unit_type.morale * 3
    if unit_type.elite:
        return base * ELITE_NUMERATOR // ELITE_DENOMINATOR
    return base


def force_points(types: Mapping[str, UnitType], keys: Mapping[str, int]) -> int:
    """The point total of a force, where `keys` counts each type key."""
    return sum(unit_points(types[key]) * count for key, count in keys.items())


def army_table(types: Mapping[str, UnitType], nationality: str) -> dict[str, int]:
    """The point value of each counter of one army, keyed the way the engine keys them."""
    out = {}
    for key, unit_type in types.items():
        if key.split(":")[0] != nationality:
            continue
        out[key] = unit_points(unit_type)
    return out
