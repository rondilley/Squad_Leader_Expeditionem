"""The legal commands of each command window, keyed by the sub-step name (M3).

`slcore.phases.PHASE_STEPS` names each window sub-step. Each window has one generator
here, registered in the table of `slcore.actions` with `actions.window`. A generator takes
the engine, the state, and the sub-step, and gives the commands in their frame sequence.
The fire window is in `slcore.fire_window`.

The sequence of the commands is part of the behaviour: an agent that picks by position,
such as the random agent, depends on it. So each generator keeps the sequence of the
engine before the table.
"""

from __future__ import annotations

from typing import Any

from slcore import actions
from slcore.commands import Command
from slcore.game import State
from slcore.phases import SubStep
from slcore.rules import (
    r05_movement,
    r06_stacking,
    r13_rout,
    r14_rally,
    r18_berserk,
    r20_close_combat,
    r21_setup,
    r23_demolition,
    r24_smoke,
    r25_concealment,
    r27_sewer,
    r28_vehicles,
    r30_vehicle_movement,
    r31_transport,
    r35_overrun,
    r36_infantry_vs_afv,
    r38_fate,
)


# ------------------------------------------------------------------ set up


@actions.window("place")
def setup_commands(engine: Any, state: State, step: SubStep) -> list[Command]:
    """Rule 21.2 with the concealment counters that rule 25.6 gives the scenario.

    Rule 25.6 says the counters of a scenario are placed during set up, so the side
    cannot declare set up complete while it holds one.
    """
    out = r21_setup.legal_setup(engine.scenario, engine.board, engine.types, state)
    if engine.has_vehicles:
        out = _with_vehicle_facings(engine, state, out)
    left = r25_concealment.counters_left(state, state.active, engine.concealment_allowance())
    if left <= 0:
        return out
    out = [c for c in out if c.action != "end_setup"]
    placed = {c.hex for c in state.concealment if c.player == state.active}
    for hex_ref in engine._concealment_hexes(state, state.active):
        if hex_ref in placed and left < 2:
            continue
        out.append(Command("place_concealment", hex=hex_ref))
    return out


def _with_vehicle_facings(engine: Any, state: State, commands: list[Command]) -> list[Command]:
    """Rules 29.1, 30.1, and PR-21: a vehicle is placed on a legal hex with a facing."""
    out: list[Command] = []
    for command in commands:
        if command.action != "place" or not command.units:
            out.append(command)
            continue
        unit = state.units[command.units[0]]
        if not unit.is_vehicle or command.hex is None:
            out.append(command)
            continue
        # Rule 30.1: no vehicle enters a stone building hex, and rule 29.1 puts one
        # vehicle in a hex.
        if engine.board.hex(command.hex).terrain == "stone_building":
            continue
        standing = r28_vehicles.vehicle_in(state, command.hex)
        if standing is not None and standing.id != unit.id:
            continue
        for facing in range(6):
            out.append(Command("place", units=command.units, hex=command.hex, extra=(("facing", facing),)))
    return out


# ------------------------------------------------------------------ the rare windows


@actions.window("smoke_window")
def smoke_commands(engine: Any, state: State, step: SubStep) -> list[Command]:
    """Rules 24.2 and 24.3: an engineer squad puts one counter in or next to its hex."""
    out: list[Command] = []
    for unit in sorted(state.player_units(state.active), key=lambda u: u.id):
        if not r24_smoke.can_place(state, engine.types, unit):
            continue
        for hex_ref in r24_smoke.target_hexes(engine.board, unit):
            out.append(Command("place_smoke", units=(unit.id,), hex=hex_ref))
    return out + [Command("end_phase")]


@actions.window("demo_window")
def demo_commands(engine: Any, state: State, step: SubStep) -> list[Command]:
    """Rule 23.4: the owner explodes a charge in the Advancing Fire Phase, or does not."""
    out = [
        Command("explode_demo", hex=c.hex, extra=(("charge", c.id),))
        for c in r23_demolition.ready(state, state.active)
    ]
    return out + [Command("end_phase")]


@actions.window("sewer_return")
def sewer_return_commands(engine: Any, state: State, step: SubStep) -> list[Command]:
    """Rule 27.22: the opposing player names the entrance the lost stack comes up at."""
    party = r27_sewer.lost_party(state)
    if party is None:
        return [Command("end_phase")]
    out = [Command("sewer_return", hex=h) for h in r27_sewer.lost_destinations(engine.board, state, party.start)]
    return out or [Command("end_phase")]


@actions.window("push_out")
def push_out_commands(engine: Any, state: State, step: SubStep) -> list[Command]:
    """Rule 35.8 and PR-51: each unit with a hex to step into must step.

    The window closes when none is left, and the units with no hex are then eliminated.
    """
    pushes = r35_overrun.legal_pushes(engine.board, state, engine.types, state.active)
    return pushes or [Command("end_phase")]


# ------------------------------------------------------------------ the phases


@actions.window("rally_window")
def rally_commands(engine: Any, state: State, step: SubStep) -> list[Command]:
    commands = r14_rally.legal_rally_commands(state, state.active, engine.types)
    if engine.has_vehicles:
        # Rule 38.1 repairs a gun and rule 40.4 pushes a wreck out of the way.
        commands.extend(r38_fate.legal_repairs(state, state.active))
        commands.extend(r38_fate.legal_wreck_pushes(state, engine.board, state.active))
    return commands + [Command("end_phase")]


@actions.window("move_window")
def movement_commands(engine: Any, state: State, step: SubStep) -> list[Command]:
    # Rule 18.42 (PR-37): a berserk unit moves on its charge. While a charge has a step to
    # make, the window holds that step and nothing else, so the phase cannot stall on
    # other commands before the charge is made.
    free, forced = r18_berserk.charge_moves(engine.move_ctx, state, engine._sees_fn(state))
    if forced:
        return forced
    commands = r05_movement.legal_moves(engine.move_ctx, state)
    commands.extend(free)
    commands.extend(_demo_place_commands(engine, state))
    commands.extend(_sewer_commands(engine, state))
    if engine.has_vehicles and engine.vehicle_ctx is not None:
        commands.extend(r30_vehicle_movement.legal_moves(engine.vehicle_ctx, state))
        commands.extend(r31_transport.legal_boarding(state, engine.types, state.active))
        commands.extend(r31_transport.legal_debarking(engine.board, state, engine.types, state.active))
    if _may_end_movement(engine, state, commands):
        commands.append(Command("end_phase"))
    return commands


def _may_end_movement(engine: Any, state: State, commands: list[Command]) -> bool:
    """Rule 6.3 with rule 13.44 and project ruling PR-18.

    Rule 6.3 says the units above a stacking limit must move, so the phase does not end
    while a hex is over a limit. A broken unit cannot move in the Movement Phase, so a hex
    whose excess is broken units has no relief. Rule 13.44 removes that excess in the Rout
    Phase, and the Movement Phase must be able to reach it.

    So the window closes when no hex is over a limit, or when no command of this window
    takes a unit out of a hex that is over a limit.
    """
    if engine.has_vehicles:
        # Rule 30.8: a vehicle may not stop in a hex that holds another vehicle.
        crowded = [v for v in r28_vehicles.vehicles(state, state.active) if r30_vehicle_movement.must_leave(state, v)]
        if crowded:
            ids = {v.id for v in crowded}
            if any(c.action == "vehicle_move" and c.units[0] in ids for c in commands):
                return False
    over = r06_stacking.overstacked_hexes(state, engine.types, state.active)
    if not over:
        return True
    for command in commands:
        if command.action not in ("move", "stack_move", "sewer_move"):
            continue
        if any(state.units[uid].hex in over for uid in command.units):
            return False
    return True


def _demo_place_commands(engine: Any, state: State) -> list[Command]:
    """Rule 23.3: the charge goes on a hex next to the unit, in the Movement Phase."""
    out: list[Command] = []
    for unit in sorted(state.player_units(state.active), key=lambda u: u.id):
        if unit.hex is None or unit.carrier is not None:
            continue
        for weapon in sorted(state.carried_by(unit.id), key=lambda w: w.id):
            if not r23_demolition.can_place(state, engine.types, unit, weapon):
                continue
            for hex_ref in r23_demolition.target_hexes(engine.board, unit):
                out.append(Command("place_demo", units=(unit.id,), weapon=weapon.id, hex=hex_ref))
    return out


def _sewer_commands(engine: Any, state: State) -> list[Command]:
    """Rules 27.1, 27.2, and 27.21: the stack that may go down, and where it may come up."""
    player = state.active
    out: list[Command] = []
    for hex_ref in sorted({u.hex for u in state.player_units(player) if u.hex is not None}):
        if not r27_sewer.is_entrance(engine.board, state, hex_ref):
            continue
        party = r27_sewer.party_in(state, hex_ref, player)
        if not party or not r27_sewer.party_allowed(party):
            continue
        ids = tuple(u.id for u in party)
        for target in r27_sewer.destinations(engine.board, state, hex_ref):
            out.append(Command("sewer_move", units=ids, hex=target))
    return out


@actions.window("rout_window")
def rout_commands(engine: Any, state: State, step: SubStep) -> list[Command]:
    commands = r13_rout.legal_rout_commands(engine.rout_ctx, engine.types, state, state.active)
    # Rule 13.4 and PR-36: a broken unit that must rout and can rout does so before the
    # window closes. Each rout command belongs to such a unit.
    if not any(c.action == "rout" for c in commands):
        commands.append(Command("end_phase"))
    return commands


@actions.window("advance_window")
def advance_commands(engine: Any, state: State, step: SubStep) -> list[Command]:
    free, forced = r18_berserk.charge_advances(engine.move_ctx, state, engine._sees_fn(state))
    if forced:
        return forced
    commands = r05_movement.legal_advances(engine.move_ctx, state)
    commands.extend(free)
    commands.append(Command("end_phase"))
    return commands


@actions.window("cc_declare")
def close_combat_commands(engine: Any, state: State, step: SubStep) -> list[Command]:
    commands = r20_close_combat.legal_declarations(state, engine.types, state.active)
    if engine.has_vehicles:
        # Rule 36.2: infantry that advanced onto a vehicle attacks it here.
        commands.extend(r36_infantry_vs_afv.legal_close_combat(engine.board, state, engine.types, state.active))
    # Rule 18.42 (PR-37): a berserk unit that can attack must attack.
    if not r18_berserk.must_attack(state, commands):
        commands.append(Command("end_phase"))
    return commands
