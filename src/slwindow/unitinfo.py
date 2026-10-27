"""The "about this unit" text of the windows: what the counter of a unit says, in words.

The text comes from the unit of the view that the host sent and from nothing else, so a
window shows only what its player may know (AR-09) and holds no rule table (AR-06). The
values are the values of the counter face; the text names each one.
"""

from __future__ import annotations

from typing import Any

_ARMIES = {"german": "German", "russian": "Russian", "american": "American"}
_KINDS = {
    "squad": "Squad",
    "crew": "Crew",
    "leader": "Leader",
    "sw": "Support weapon",
    "vehicle": "Vehicle",
}
_WEAPON_CLASSES = {
    "mg": "machine gun",
    "flamethrower": "flamethrower",
    "demo": "demolition charge",
    "bazooka": "bazooka",
    "panzerfaust": "panzerfaust",
}


def title(unit: dict[str, Any]) -> str:
    """The army, the counter type, and the kind, for example "Russian 4-4-7 squad"."""
    army = _ARMIES.get(str(unit.get("nationality", "")), str(unit.get("nationality", "")).title())
    kind = _KINDS.get(str(unit.get("kind", "")), str(unit.get("kind", "")))
    counter = str(unit.get("type", ""))
    return " ".join(part for part in (army, counter, kind.lower()) if part)


def _halves(value: Any) -> str:
    """A value in half points, as text: 3, or 3.5."""
    halves = int(value or 0)
    return str(halves // 2) if halves % 2 == 0 else f"{halves // 2}.5"


def _by_id(view: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
    return {int(u["id"]): u for u in (view or {}).get("units", []) or [] if isinstance(u, dict) and u.get("id") is not None}


def facts(unit: dict[str, Any], view: dict[str, Any] | None = None) -> list[str]:
    """The lines of the "about this unit" panel. With the view, the text also names the
    unit that carries a weapon and the weapons that a unit carries."""
    kind = str(unit.get("kind", ""))
    lines: list[str] = []
    units = _by_id(view)
    if kind in ("squad", "crew"):
        lines.append(f"Firepower {unit.get('firepower')}: the strength of its fire attack.")
        lines.append(f"Normal range {unit.get('range')} hexes.")
        lines.append(f"Morale {unit.get('morale')}: it passes a morale check on this number or less.")
        if unit.get("elite"):
            lines.append("Elite unit.")
        lines.extend(_carry_lines(unit, units))
    elif kind == "leader":
        modifier = int(unit.get("leadership") or 0)
        lines.append(f"Morale {unit.get('morale')}.")
        if modifier:
            lines.append(f"Leadership {modifier:+d}: it adds this to the dice of the units it directs.")
        else:
            lines.append("Leadership 0: it does not change the dice of the units it directs.")
        lines.extend(_carry_lines(unit, units))
    elif kind == "sw":
        weapon = _WEAPON_CLASSES.get(str(unit.get("weapon_class", "")), "weapon")
        if "portage_leader_halves" in unit and unit.get("portage_leader_halves") is None:
            lines.append(f"A {weapon}. A squad carries it and fires it. A leader cannot carry it.")
        else:
            lines.append(f"A {weapon}. A squad or a leader carries it and fires it.")
        if unit.get("portage_halves"):
            leader = unit.get("portage_leader_halves")
            more = f", {_halves(leader)} for a leader" if leader is not None else ""
            lines.append(f"Portage {_halves(unit['portage_halves'])} for a squad{more}: the cost to carry it. A load above the free portage of the carrier costs movement factors.")
        if unit.get("firepower"):
            lines.append(f"Firepower {unit.get('firepower')}, normal range {unit.get('range')} hexes.")
        if unit.get("breakdown"):
            lines.append(f"Breakdown {unit.get('breakdown')}: it malfunctions on a fire roll of this number or more.")
        lines.extend(_weapon_lines(unit, units))
    elif kind == "vehicle":
        lines.append(f"Movement points {unit.get('movement_points')}.")
        if unit.get("gun"):
            lines.append(f"Main gun {unit.get('gun')} mm.")
        if unit.get("mg_ca") or unit.get("mg_360"):
            lines.append(f"Machine gun firepower: {unit.get('mg_ca', 0)} in its covered arc, {unit.get('mg_360', 0)} all around.")
        if unit.get("open_top"):
            lines.append("Open top.")
        if unit.get("transport_pp"):
            lines.append(f"Carries passengers (transport {unit.get('transport_pp')}).")
    lines.extend(state_lines(unit))
    return lines


def _weapon_lines(weapon: dict[str, Any], units: dict[int, dict[str, Any]]) -> list[str]:
    """Who carries the weapon, and how it moves."""
    carrier = weapon.get("carrier")
    if carrier is not None:
        name = units.get(int(carrier), {}).get("type", "unit")
        return [f"Carried by the {name}. It moves with that unit, and the {name} fires it."]
    if weapon.get("hex"):
        return ["No unit carries it. A squad or a leader in its hex must pick it up in the Movement Phase. Then it moves with that unit."]
    return ["In the set up, drag it onto a unit that can carry it."]


def _carry_lines(unit: dict[str, Any], units: dict[int, dict[str, Any]]) -> list[str]:
    """The weapons that the unit carries, and its movement factors with them."""
    carried = [units.get(int(w), {}).get("type", "weapon") for w in unit.get("carries", []) or []]
    if not carried:
        return []
    lines = [f"Carries the {' and the '.join(carried)}. They move with it."]
    if "movement_halves" in unit:
        moves = _halves(unit["movement_halves"])
        free = _halves(unit.get("movement_free_halves"))
        text = f"Movement factors {moves} with this load ({free} with no load)."
        if "movement_stack_halves" in unit:
            text += f" {_halves(unit['movement_stack_halves'])} when it moves in a stack with a leader."
        lines.append(text)
    return lines


def state_lines(unit: dict[str, Any]) -> list[str]:
    """What is true of the unit now: its hex, a broken side, a fire or a move done."""
    lines = []
    here = unit.get("hex")
    lines.append(f"In hex {here}." if here else "Not on the board yet.")
    if unit.get("broken"):
        lines.append("Broken: it cannot fire, and it moves only to rout, until it rallies.")
    if unit.get("berserk"):
        lines.append("Berserk.")
    if unit.get("dm"):
        lines.append("Desperation morale.")
    if unit.get("malfunction"):
        lines.append("Malfunctioned: it cannot fire until it is repaired.")
    if unit.get("prep_fired"):
        lines.append("It fired in this player turn.")
    if unit.get("moved"):
        lines.append("It moved in this player turn.")
    if unit.get("wreck"):
        lines.append("Wreck.")
    elif unit.get("immobilized"):
        lines.append("Immobilized.")
    return lines
