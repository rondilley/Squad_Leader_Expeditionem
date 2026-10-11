"""What kind of fire an event shows: rifles, a submachine gun, a machine gun, a flamethrower,
a rocket, a tank gun, a demolition charge, smoke, grenades, or an overrun.

The window animates each kind in its own way (see `effects.py`). This module only sorts the
events of the action log into shots: the kind, the hex it comes from, the hex it goes to, a
size, and for a gun whether it hit. Each fact is a fact of the event or of the unit the view
holds (its counter type and range). It reads no rule and decides no result (AR-06). It
imports no part of Panda3D, so a test reads it with no window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

RIFLE = "rifle"
SMG = "smg"
MG = "mg"
FLAME = "flame"
ROCKET = "rocket"
GUN = "gun"
BLAST = "blast"
SMOKE = "smoke"
GRENADES = "grenades"
OVERRUN = "overrun"

# A squad with a range of three hexes or less fires mostly submachine guns (the 6-2-8 guards
# and the 8-3-8 assault engineers); a longer range is rifles.
SMG_RANGE = 3
MACHINE_GUNS = {"LMG": 1, "MMG": 2, "HMG": 3}
ROCKETS = {"PF", "BAZ"}
FLAMETHROWER = "FT"
# The flamethrower fire of rule 22.2 is a "fire" event of that rule.
RULE_FLAMETHROWER = "22.2"


@dataclass(frozen=True)
class Shot:
    kind: str
    source: str | None
    target: str | None
    size: int = 1
    hit: bool = True
    # The army of the unit that fired (its counter nationality), for the colour of a tracer.
    army: str = ""


def _type_of(units: Mapping[int, Mapping[str, Any]], unit_id: Any) -> str:
    unit = units.get(unit_id) if unit_id is not None else None
    return str(unit.get("type", "")) if unit else ""


def _hex_of(units: Mapping[int, Mapping[str, Any]], unit_id: Any) -> str | None:
    unit = units.get(unit_id) if unit_id is not None else None
    if not unit:
        return None
    hex_id = unit.get("hex")
    return str(hex_id) if hex_id else None


def _army_of(units: Mapping[int, Mapping[str, Any]], unit_id: Any) -> str:
    unit = units.get(unit_id) if unit_id is not None else None
    return str(unit.get("nationality", "")) if unit else ""


def _member_shot(member: Mapping[str, Any], target: str | None, units: Mapping[int, Mapping[str, Any]], rule: str) -> Shot:
    shot = _member_kind(member, target, units, rule)
    return Shot(shot.kind, shot.source, shot.target, shot.size, shot.hit, _army_of(units, member.get("unit")))


def _member_kind(member: Mapping[str, Any], target: str | None, units: Mapping[int, Mapping[str, Any]], rule: str) -> Shot:
    source = _hex_of(units, member.get("unit"))
    weapon = member.get("weapon")
    if weapon is not None:
        name = _type_of(units, weapon)
        if name == FLAMETHROWER or rule == RULE_FLAMETHROWER:
            return Shot(FLAME, source, target)
        if name in MACHINE_GUNS:
            return Shot(MG, source, target, MACHINE_GUNS[name])
        return Shot(RIFLE, source, target)
    if rule == RULE_FLAMETHROWER:
        return Shot(FLAME, source, target)
    unit = units.get(member.get("unit"), {})
    reach = unit.get("range")
    if isinstance(reach, int) and reach and reach <= SMG_RANGE:
        return Shot(SMG, source, target)
    return Shot(RIFLE, source, target)


def shots_for(event: Mapping[str, Any], units: Mapping[int, Mapping[str, Any]]) -> list[Shot]:
    """The shots that one event shows, in the order to play them. `units` maps a unit ID to
    the unit document of the view (type, kind, range, hex). An event about a unit the view
    does not hold still shows, from no source hex, so its target still gets its effect."""
    kind = str(event.get("kind", ""))
    rule = str(event.get("rule_id", ""))
    data = event.get("data") or {}
    if kind == "fire":
        target = data.get("target")
        return [_member_shot(m, target, units, rule) for m in data.get("members", []) if isinstance(m, Mapping)]
    if kind == "afv_mg_fire":
        unit = data.get("unit")
        return [Shot(MG, _hex_of(units, unit), data.get("target"), 2, True, _army_of(units, unit))]
    if kind == "to_hit":
        unit = data.get("unit")
        return [Shot(GUN, _hex_of(units, unit), data.get("target"), 3, bool(data.get("hit")), _army_of(units, unit))]
    if kind == "at_to_hit":
        size = 2 if _type_of(units, data.get("weapon")) == "BAZ" else 1
        unit = data.get("unit")
        return [
            Shot(ROCKET, _hex_of(units, unit), _hex_of(units, data.get("vehicle")), size, bool(data.get("hit")), _army_of(units, unit))
        ]
    if kind == "demo_explode":
        return [Shot(BLAST, None, data.get("hex"), 3)]
    if kind == "grenade_bundle":
        return [Shot(BLAST, None, _hex_of(units, data.get("unit")), 1)]
    if kind == "smoke":
        return [Shot(SMOKE, _hex_of(units, data.get("unit")), data.get("hex"))]
    if kind == "afv_smoke":
        # Rule 41.3: the gun fires a smoke round into a hex.
        return [Shot(SMOKE, _hex_of(units, data.get("unit")), data.get("hex"), 2)]
    if kind == "smoke_dischargers":
        # Rule 41.4: the dischargers put smoke on the tank's own hex.
        return [Shot(SMOKE, None, data.get("hex"))]
    if kind in ("cc_kill", "cc_miss"):
        targets = [_hex_of(units, t) for t in data.get("targets", [])]
        where = next((t for t in targets if t), None)
        return [Shot(GRENADES, None, where, 2 if kind == "cc_kill" else 1)]
    if kind == "overrun":
        return [Shot(OVERRUN, None, data.get("hex"))]
    return []
