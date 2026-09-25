"""Rule 23, demolition charges.

A demolition charge is a support weapon that an assault engineer squad, or a leader of
minus two or better, puts on a hex next to itself during its Movement Phase (rules 23.2
and 23.3). The charge is not an attack at that moment. It waits.

The unit that placed it must live through the Defensive Fire Phase in its placement hex
without breaking. If it breaks there the charge stays in that hex and does not explode
(rule 23.3). If it holds, the owner explodes the charge in the Advancing Fire Phase that
follows, with 30 firepower on the Infantry Fire Table (rules 23.1 and 23.4).

The dice roll modifiers are the protective cover of the target hex and nothing else.
Leadership does not help the charge, and a concealed unit is attacked at half strength
(rule 23.5).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from slcore import actions, geometry
from slcore.commands import Command
from slcore.events import Event
from slcore.game import DemoCharge, State
from slcore.geometry import HexRef
from slcore.rng import roll_2d6
from slcore.rules import r10_resolution, r11_terrain, r27_sewer, r33_afv_combat, r37_at_weapons
from slcore.state import Board
from slcore.units import KIND_LEADER, KIND_SW, Unit, UnitType

RULE_23_1 = "23.1"
RULE_23_2 = "23.2"
RULE_23_3 = "23.3"
RULE_23_4 = "23.4"
RULE_23_5 = "23.5"
RULE_23_6 = "23.6"
RULE_23_7 = "23.7"
RULE_23_8 = "23.8"

WEAPON_CLASS = "demo"
MALFUNCTION_ROLL = 12
LEADER_RATING = -2
# PR-46: the column of the kill table that a charge reads against a vehicle (rule 33.4).
KILL_COLUMN = "demolition_charge"


def is_charge(types: Mapping[str, UnitType], unit: Unit) -> bool:
    return unit.kind == KIND_SW and types[unit.type_key].weapon_class == WEAPON_CLASS


def may_place(types: Mapping[str, UnitType], unit: Unit) -> bool:
    """Rule 23.2: an assault engineer squad, or a leader of minus two or better."""
    t = types[unit.type_key]
    if t.assault_engineer:
        return True
    return unit.kind == KIND_LEADER and t.leadership <= LEADER_RATING


def can_place(state: State, types: Mapping[str, UnitType], unit: Unit, weapon: Unit) -> bool:
    """Rule 23.3: the unit carries the charge, it is not broken, and it has not placed one."""
    if not is_charge(types, weapon) or weapon.carrier != unit.id or weapon.eliminated:
        return False
    if unit.broken or unit.hex is None or state.in_melee(unit.hex) or unit.demo_placed:
        return False
    return may_place(types, unit)


def target_hexes(board: Board, unit: Unit) -> list[HexRef]:
    """Rule 23.3: a hex next to the unit. The unit does not stay next to it."""
    if unit.hex is None:
        return []
    return sorted(h for h in geometry.neighbors(*unit.hex) if h in board)


def place(state: State, unit_id: int, weapon_id: int, hex_ref: HexRef) -> tuple[State, list[Event]]:
    """Rule 23.3: the charge goes on the target hex and waits for the Advancing Fire Phase."""
    unit = state.units[unit_id]
    if unit.hex is None:
        raise ValueError("a demolition charge needs a unit on the board")
    charge = DemoCharge(state.next_marker, unit.player, hex_ref, unit_id, unit.hex, weapon_id)
    state = state.with_(demo=state.demo + (charge,), next_marker=state.next_marker + 1)
    weapon = state.units[weapon_id]
    state = state.with_units({unit_id: state.units[unit_id].with_(demo_placed=True), weapon_id: weapon.with_(carrier=None, hex=None)})
    return state, [
        Event(
            RULE_23_3,
            "demo_placed",
            {
                "charge": charge.id,
                "unit": unit_id,
                "weapon": weapon_id,
                "hex": geometry.hex_id(*hex_ref),
                "from": geometry.hex_id(*unit.hex),
            },
        )
    ]


def arm(state: State) -> tuple[State, list[Event]]:
    """Rule 23.3 at the end of the Defensive Fire Phase: which charges are operable.

    A charge whose placer broke in the placement hex, or left it, or was eliminated, does
    not explode (PR-14). It leaves the target hex and lies as a support weapon on the
    ground in the placement hex, so no later phase tests it again or arms it.
    """
    events: list[Event] = []
    out = []
    dropped: dict[int, Unit] = {}
    for charge in state.demo:
        if charge.armed:
            out.append(charge)
            continue
        placer = state.units[charge.placer]
        ok = not placer.eliminated and not placer.broken and placer.hex == charge.placed_from
        data = {"charge": charge.id, "unit": charge.placer, "hex": geometry.hex_id(*charge.hex)}
        if ok:
            out.append(replace(charge, armed=True))
        else:
            weapon = state.units[charge.weapon]
            dropped[weapon.id] = weapon.with_(hex=charge.placed_from, carrier=None)
            data["left_in"] = geometry.hex_id(*charge.placed_from)
        events.append(Event(RULE_23_3, "demo_armed" if ok else "demo_dud", data))
    state = state.with_(demo=tuple(out))
    return (state.with_units(dropped) if dropped else state), events


def ready(state: State, player: int) -> tuple[DemoCharge, ...]:
    """Rule 23.4: the charges of this player that may explode in this Advancing Fire Phase."""
    return tuple(c for c in state.demo if c.player == player and c.armed)


def remove(state: State, charge_id: int) -> State:
    return state.with_(demo=tuple(c for c in state.demo if c.id != charge_id))


def halves(types: Mapping[str, UnitType], weapon_key: str) -> int:
    """Rule 23.1: 30 factors on the Infantry Fire Table, in half factors (NFR-05)."""
    return types[weapon_key].firepower * 2


def roll(state: State) -> tuple[State, tuple[int, int]]:
    rng, dice = roll_2d6(state.rng)
    return state.with_(rng=rng), dice


# ------------------------------------------------------------------ the command handlers (M3)


@actions.action("place_demo", unconceals=actions.CAUSE_CHARGE)
def _on_place_demo(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    if command.hex is None or command.weapon is None:
        raise ValueError("a demolition charge needs a hex and a weapon")
    return place(state, command.units[0], command.weapon, command.hex)


@actions.action("explode_demo")
def _on_explode_demo(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    """Rules 23.1, 23.4, 23.5, 23.7, and 23.8: the charge goes off in its hex."""
    charge_id = dict(command.extra).get("charge")
    charge = next((c for c in state.demo if c.id == charge_id), None)
    if charge is None:
        raise ValueError(f"there is no demolition charge {charge_id}")
    weapon_key = state.units[charge.weapon].type_key
    state, dice = roll(state)
    raw = dice[0] + dice[1]
    charge_halves = halves(engine.types, weapon_key)
    drm = r11_terrain.target_hex_modifier(engine.board, charge.hex)
    events = [
        Event(
            RULE_23_1,
            "demo_explode",
            {
                "charge": charge.id,
                "hex": geometry.hex_id(*charge.hex),
                "firepower": charge_halves // 2,
                "dice": list(dice),
                "modifiers": [{"rule": RULE_23_5, "value": drm, "cause": "protective cover"}],
                "adjusted": raw + drm,
            },
        )
    ]
    state = remove(state, charge.id)
    state = state.with_unit(state.units[charge.weapon].with_(eliminated=True, hex=None, carrier=None))
    if raw == MALFUNCTION_ROLL:
        events.append(Event(RULE_23_8, "demo_dud", {"charge": charge.id, "roll": raw}))
        return state, events
    if engine.has_vehicles:
        # PR-46: the explosion roll is the kill roll against each vehicle of the hex, on the
        # demolition charge column, from the side the charge was placed against.
        for vehicle in [u for u in state.units_in(charge.hex) if u.is_vehicle and not u.wreck]:
            kill = r33_afv_combat.kill_with_roll(engine.armor_ctx, charge.placed_from, vehicle, KILL_COLUMN, raw)
            events.append(r33_afv_combat.kill_event(charge.placer, vehicle, kill))
            state, ev = r37_at_weapons.kill_result(
                engine.armor_ctx, state, state.units[vehicle.id], kill, "a demolition charge (PR-46)"
            )
            events.extend(ev)
    state, hit = r10_resolution.apply_to_hex(
        engine.fire_ctx, state, charge.hex, charge_halves, raw, drm, state.phase, charge.player, affect_all=True, kill_weapons=True
    )
    events.extend(hit)
    if r27_sewer.is_entrance(engine.board, state, charge.hex):
        state = r27_sewer.close(state, charge.hex)
        events.append(Event(r27_sewer.RULE_27_6, "sewer_closed", {"hex": geometry.hex_id(*charge.hex)}))
    return state, events
