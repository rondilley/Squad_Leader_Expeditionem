"""Rule 12, morale, with the berserk rule of 18.4 and 18.5."""

from __future__ import annotations

from typing import Mapping

from slcore import geometry
from slcore.events import Event
from slcore.game import State
from slcore.rng import roll_2d6
from slcore.rules import r15_leadership, r26_fanaticism
from slcore.units import KIND_LEADER, Unit, UnitType

RULE_12_1 = "12.1"
RULE_12_21 = "12.21"
RULE_12_22 = "12.22"
RULE_12_3 = "12.3"
RULE_12_4 = "12.4"
RULE_13_6 = "13.6"
RULE_18_4 = "18.4"
RULE_18_5 = "18.5"

BERSERK_ROLL = 2
RUSSIAN = "russian"


def morale_value(types: Mapping[str, UnitType], unit: Unit) -> int:
    t = types[unit.type_key]
    return t.broken_morale if unit.broken else t.morale


def morale_check(state: State, types: Mapping[str, UnitType], unit: Unit, modifier: int, cause: str) -> tuple[State, list[Event]]:
    """One morale check (rule 12.1). A failure breaks the unit, and a broken unit is removed."""
    if unit.eliminated or unit.berserk:
        return state, []
    state_rng, dice = roll_2d6(state.rng)
    state = state.with_(rng=state_rng)
    raw = dice[0] + dice[1]
    leader_mod, leader_id = r15_leadership.modifier_for_check(state, types, unit)
    fanatic = r26_fanaticism.modifier_for(state, unit)
    adjusted = raw + modifier + leader_mod + fanatic
    target = morale_value(types, unit)
    events: list[Event] = []
    data = {
        "unit": unit.id,
        "hex": geometry.hex_id(*unit.hex) if unit.hex else None,
        "dice": list(dice),
        "modifier": modifier,
        "leadership": leader_mod,
        "leader": leader_id,
        "fanatic": fanatic,
        "adjusted": adjusted,
        "morale": target,
        "cause": cause,
    }
    if types[unit.type_key].nationality == RUSSIAN and raw == BERSERK_ROLL and cause == "fire":
        state, berserk_events = go_berserk(state, types, unit)
        return state, [Event(RULE_18_4, "berserk", data)] + berserk_events
    if adjusted <= target:
        events.append(Event(RULE_12_1, "morale_pass", data))
        return state, events
    if unit.broken:
        state, drop_events = drop_weapons(state, unit.id)
        state = state.with_unit(state.units[unit.id].with_(eliminated=True, hex=None, carrier=None))
        events.append(Event(RULE_13_6, "eliminated", data))
        return state, events + drop_events
    broken = state.units[unit.id].with_(broken=True, prep_fired=False, fired=False, directed=False, manned_mg=False)
    state = state.with_unit(broken)
    state, drop_events = drop_weapons(state, unit.id)
    events.append(Event(RULE_12_3, "broken", data))
    events.extend(drop_events)
    if unit.kind == KIND_LEADER:
        state, cascade = leader_break_cascade(state, types, unit)
        events.extend(cascade)
    return state, events


def drop_weapons(state: State, unit_id: int) -> tuple[State, list[Event]]:
    """Rule 13.5: a broken unit abandons the support weapons it carried."""
    events: list[Event] = []
    changed = {}
    carrier = state.units[unit_id]
    for w in state.carried_by(unit_id):
        changed[w.id] = w.with_(carrier=None, hex=carrier.hex)
        events.append(Event("13.5", "abandon_weapon", {"unit": unit_id, "weapon": w.id}))
    if changed:
        state = state.with_units(changed)
    return state, events


def leader_break_cascade(state: State, types: Mapping[str, UnitType], leader: Unit) -> tuple[State, list[Event]]:
    """Rule 12.22: each leader that breaks causes one more normal check for the other units in the hex."""
    if leader.hex is None:
        return state, []
    events: list[Event] = []
    for other in sorted(state.infantry_in(leader.hex), key=lambda u: (u.kind != KIND_LEADER, u.id)):
        if other.id == leader.id or other.player != leader.player or other.eliminated:
            continue
        state, ev = morale_check(state, types, state.units[other.id], 0, "leader_break")
        events.extend(ev)
    return state, events


def go_berserk(state: State, types: Mapping[str, UnitType], unit: Unit) -> tuple[State, list[Event]]:
    """Rule 18.4: the unit is berserk. Rule 18.42 gives the unit more movement and no morale checks."""
    events: list[Event] = []
    changed = {unit.id: state.units[unit.id].with_(berserk=True, broken=False)}
    state = state.with_units(changed)
    state, drop_events = drop_excess_portage(state, types, unit.id)
    events.extend(drop_events)
    if unit.kind == KIND_LEADER and unit.hex is not None:
        for other in sorted(state.infantry_in(unit.hex), key=lambda u: u.id):
            if other.id == unit.id or other.player != unit.player or other.broken or other.berserk:
                continue
            state, ev = desperation_join(state, types, state.units[other.id], unit)
            events.extend(ev)
    return state, events


def desperation_join(state: State, types: Mapping[str, UnitType], unit: Unit, leader: Unit) -> tuple[State, list[Event]]:
    """Rule 18.5: units with a berserk leader may join on a desperation morale roll."""
    state_rng, dice = roll_2d6(state.rng)
    state = state.with_(rng=state_rng)
    raw = dice[0] + dice[1]
    modifier = types[leader.type_key].leadership
    target = morale_value(types, unit) - 4
    data = {"unit": unit.id, "leader": leader.id, "dice": list(dice), "target": target, "adjusted": raw + modifier}
    if raw + modifier <= target:
        state, ev = go_berserk(state, types, state.units[unit.id])
        return state, [Event(RULE_18_5, "berserk_join", data)] + ev
    return state, [Event(RULE_18_5, "berserk_join_failed", data)]


def drop_excess_portage(state: State, types: Mapping[str, UnitType], unit_id: int) -> tuple[State, list[Event]]:
    """The ruling for 18.42: a berserk unit keeps only the portage that does not reduce its movement."""
    unit = state.units[unit_id]
    free = types[unit.type_key].free_portage_halves
    carried = sorted(state.carried_by(unit_id), key=lambda w: w.id)
    total = 0
    events: list[Event] = []
    changed = {}
    for w in carried:
        cost = types[w.type_key].portage_leader_halves if unit.kind == KIND_LEADER else types[w.type_key].portage_squad_halves
        cost = cost if cost is not None else 99
        if total + cost <= free:
            total += cost
            continue
        changed[w.id] = w.with_(carrier=None, hex=unit.hex)
        events.append(Event("18.42", "abandon_weapon", {"unit": unit_id, "weapon": w.id}))
    if changed:
        state = state.with_units(changed)
    return state, events
