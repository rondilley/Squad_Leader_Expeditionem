"""Rule 5, movement, and the Advance Phase move of rules 4.7 and 5.73.

Movement factors are in halves (NFR-05). A squad has 8 halves, a leader 12.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from slcore import actions, geometry
from slcore.commands import Command
from slcore.events import Event
from slcore.game import State
from slcore.geometry import HexRef
from slcore.rules import r06_stacking, r42_hidden
from slcore.state import Board, HexsideRule, TerrainType
from slcore.units import (
    KIND_LEADER,
    KIND_SW,
    MOVE_MODE_NONE,
    MOVE_MODE_SOLO,
    MOVE_MODE_STACK,
    Unit,
    UnitType,
)

RULE_5_2 = "5.2"
RULE_5_44 = "5.44"
RULE_5_5 = "5.5"
RULE_5_51 = "5.51"
RULE_5_52 = "5.52"
RULE_5_53 = "5.53"
RULE_5_6 = "5.6"
RULE_5_7 = "5.7"
RULE_5_71 = "5.71"
RULE_5_73 = "5.73"
RULE_4_7 = "4.7"
RULE_13_5 = "13.5"

LEADER_BONUS_HALVES = 4
LEADER_MAX_PORTAGE = 3
ADVANCE_SQUAD_PORTAGE = 5
ADVANCE_LEADER_PORTAGE = 3
MOVE_MODE_ADVANCED = "advanced"
# Rule 18.43 in halves: a berserk squad has 6 movement factors, a berserk leader 8, and a
# berserk squad in a stack with a berserk leader 8.
BERSERK_SQUAD_HALVES = 12
BERSERK_LEADER_HALVES = 16
# PR-38: rule 50.4 lets an American unit operate each captured support weapon.
NATION_OPERATES_ALL_CAPTURED = "american"
WEAPON_CLASS_MG = "mg"


@dataclass(frozen=True)
class MoveContext:
    board: Board
    terrain: Mapping[str, TerrainType]
    hexsides: Mapping[str, HexsideRule]
    types: Mapping[str, UnitType]


def weapon_portage_halves(ctx: MoveContext, state: State, unit: Unit) -> int:
    """Rule 5.7: the portage the unit carries, in half points.

    Rule 37.35 gives the panzerfaust half the cost of a machine gun, so the sum is in
    halves in the same way the movement factors are (NFR-05).
    """
    total = 0
    for w in state.carried_by(unit.id):
        t = ctx.types[w.type_key]
        if unit.kind == KIND_LEADER:
            leader = t.portage_leader_halves
            total += leader if leader is not None else 198
        else:
            total += t.portage_squad_halves
    return total


def weapon_portage(ctx: MoveContext, state: State, unit: Unit) -> int:
    """Rule 5.7 in whole points, for the limits that the rules state in whole points."""
    return weapon_portage_halves(ctx, state, unit) // 2


def in_stack_with_leader(state: State, unit: Unit) -> bool:
    return unit.kind != KIND_LEADER and unit.move_mode.startswith(MOVE_MODE_STACK)


def allowance_halves(ctx: MoveContext, state: State, unit: Unit, leader_bonus: bool) -> int:
    """Rules 5.41, 5.42, 5.44, 5.7: base factors, the leader bonus, the portage penalty.

    Rule 18.43 gives a berserk unit its own factors: 6 for a squad, 8 for a leader, and 8
    for a squad that moves in a stack with a berserk leader. `leader_bonus` is that stack
    for a berserk squad.
    """
    t = ctx.types[unit.type_key]
    halves = t.mf_halves
    if unit.berserk:
        if unit.kind == KIND_LEADER or leader_bonus:
            halves = BERSERK_LEADER_HALVES
        else:
            halves = BERSERK_SQUAD_HALVES
    elif leader_bonus and unit.kind != KIND_LEADER:
        halves += LEADER_BONUS_HALVES
    excess = weapon_portage_halves(ctx, state, unit) - t.free_portage_halves
    if excess > 0:
        halves -= excess
    return halves


# The name of the memo of entry costs that a MoveContext keeps. It is not a field.
_COST_ATTRIBUTE = "_entry_costs"


def entry_cost_halves(ctx: MoveContext, src: HexRef, dst: HexRef) -> tuple[int | None, tuple[str, ...]]:
    """Rules 5.5 to 5.54: the cost to enter dst from src, and the rule IDs applied.

    The cost reads the board and the two tables of the context only, and those do not
    change, so each answer is kept on the context (NFR-01).
    """
    memo = ctx.__dict__.get(_COST_ATTRIBUTE)
    if memo is None:
        memo = ctx.__dict__[_COST_ATTRIBUTE] = {}
    key = (src, dst)
    found = memo.get(key)
    if found is None:
        found = memo[key] = _entry_cost(ctx, src, dst)
    return found


def _entry_cost(ctx: MoveContext, src: HexRef, dst: HexRef) -> tuple[int | None, tuple[str, ...]]:
    d = geometry.direction_to(src, dst)
    if d is None:
        return None, ()
    board = ctx.board
    from_hex = board.hex(src)
    to_hex = board.hex(dst)
    rules = [RULE_5_5]
    feature = from_hex.hexsides[d]
    extra = 0
    if feature is not None:
        rule = ctx.hexsides[feature]
        if not rule.passable:
            return None, (RULE_5_5,)
        extra += rule.mf_extra_halves
        if rule.mf_extra_halves:
            rules.append(RULE_5_51)
    terrain_cost = ctx.terrain[to_hex.terrain].mf_halves
    if to_hex.road and from_hex.road and to_hex.terrain == "open":
        terrain_cost = 1
        rules.append(RULE_5_52)
    if to_hex.elevation > from_hex.elevation:
        terrain_cost *= 2
        rules.append(RULE_5_53)
    return terrain_cost + extra, tuple(rules)


def enemy_in_hex(state: State, player: int, hex_ref: HexRef) -> bool:
    """Whether an enemy unit that the moving player can see is in this hex.

    Rule 42.1 keeps a hidden unit off the board that the other player sees, so a hidden
    unit does not make a hex illegal to enter. Rule 42.5 stops the move when it happens,
    and the moving player learns of the hidden unit at that moment and not before.

    Rule 25.2 treats each concealment counter of the other side as an opposing squad,
    whether a unit is below it or not (PR-31). So the counter makes the hex an enemy hex,
    and a dummy of rule 25.7 gives the same answer as a real stack.
    """
    if state.enemy_counter_in(hex_ref, player):
        return True
    return any(
        u.player != player for u in state.units_in(hex_ref) if u.kind != KIND_SW and not u.hidden
    )


def _can_exit_after(ctx: MoveContext, state: State, unit: Unit, dst: HexRef, remaining: int) -> bool:
    """PR-04: a unit may enter an over-limit hex only with factors left to leave it."""
    for n in ctx.board.neighbors(dst):
        if enemy_in_hex(state, unit.player, n):
            continue
        cost, _ = entry_cost_halves(ctx, dst, n)
        if cost is None or cost > remaining:
            continue
        if not r06_stacking.rule_6_1_overstacked(state, ctx.types, n, unit.player, extra_ids=(unit.id,)):
            return True
    return False


def movers(state: State, player: int) -> list[Unit]:
    """Rules 4.3 and 5.1: unbroken infantry of the phasing player that did not prep fire.

    Rule 15.2 also holds a leader in place when it directed a fire group in the Prep
    Fire Phase, so the `directed` flag stops it here. Rule 27.2 ends the Movement Phase
    of a unit that made a sewer move at its entrance (PR-35).
    """
    return [
        u
        for u in state.player_units(player)
        if u.is_infantry and u.hex is not None and u.carrier is None and not u.broken and not u.prep_fired and not u.directed and not u.sewer_move and not state.in_melee(u.hex)
    ]


def stack_members(state: State, leader: Unit) -> list[Unit]:
    tag = f"{MOVE_MODE_STACK}{leader.id}"
    return [u for u in state.units if u.move_mode == tag and u.id != leader.id and not u.eliminated]


def legal_moves(ctx: MoveContext, state: State) -> list[Command]:
    player = state.active
    out: list[Command] = []
    for u in movers(state, player):
        if u.hex is None:
            continue
        if u.berserk:
            # Rule 18.42: a berserk unit moves on its charge, which r18_berserk gives.
            continue
        if u.move_mode.startswith(MOVE_MODE_STACK):
            if u.kind != KIND_LEADER:
                continue
            members = stack_members(state, u)
            out.extend(_stack_moves(ctx, state, u, members))
            continue
        if u.kind == KIND_LEADER and u.move_mode == MOVE_MODE_NONE:
            candidates = [
                s
                for s in state.units_in(u.hex)
                if s.player == player and s.is_infantry and s.kind != KIND_LEADER and not s.broken and not s.prep_fired and not s.berserk and not s.sewer_move and s.move_mode == MOVE_MODE_NONE
            ]
            for subset in _subsets(candidates):
                out.extend(_stack_moves(ctx, state, u, subset))
        out.extend(_solo_moves(ctx, state, u))
    out.extend(legal_pickups_and_drops(ctx, state, in_movement=True))
    out.extend(_relief_moves(ctx, state, player, out))
    return out


def _relief_moves(ctx: MoveContext, state: State, player: int, already: list[Command]) -> list[Command]:
    """Rule 6.3: a player may exceed the stacking limits during movement.

    The normal list does not offer a move into a hex that would go above a limit, which
    keeps the list small. When the player already has a hex above a limit, that
    restriction can leave the units in it with no move, and rule 6.3 does not end the
    phase while a hex is above a limit. These moves give the units of such a hex a way
    out, whatever the load of the hex they enter.
    """
    over = r06_stacking.overstacked_hexes(state, ctx.types, player)
    if not over:
        return []
    served = {c.units[0] for c in already if c.action in ("move", "stack_move")}
    out: list[Command] = []
    for u in movers(state, player):
        if u.hex not in over or u.id in served or u.move_mode.startswith(MOVE_MODE_STACK):
            continue
        remaining = allowance_halves(ctx, state, u, leader_bonus=False) - u.mf_used
        for d in range(6):
            dst = geometry.neighbor(*u.hex, d)
            if dst not in ctx.board or enemy_in_hex(state, u.player, dst):
                continue
            cost, _ = entry_cost_halves(ctx, u.hex, dst)
            if cost is None or cost > remaining:
                continue
            out.append(Command("move", units=(u.id,), hex=dst))
    return out


def _subsets(units: list[Unit]) -> list[list[Unit]]:
    subsets: list[list[Unit]] = []
    n = len(units)
    for mask in range(1, 1 << n):
        subsets.append([units[i] for i in range(n) if mask & (1 << i)])
    return subsets


def _solo_moves(ctx: MoveContext, state: State, u: Unit) -> list[Command]:
    out: list[Command] = []
    if u.hex is None:
        return out
    allowance = allowance_halves(ctx, state, u, leader_bonus=False)
    remaining = allowance - u.mf_used
    for d in range(6):
        dst = geometry.neighbor(*u.hex, d)
        if dst not in ctx.board or enemy_in_hex(state, u.player, dst):
            continue
        cost, _ = entry_cost_halves(ctx, u.hex, dst)
        if cost is None or cost > remaining:
            continue
        if r06_stacking.rule_6_1_overstacked(state, ctx.types, dst, u.player, extra_ids=(u.id,)):
            if not _can_exit_after(ctx, state, u, dst, remaining - cost):
                continue
        out.append(Command("move", units=(u.id,), hex=dst))
    return out


def _stack_moves(ctx: MoveContext, state: State, leader: Unit, members: list[Unit]) -> list[Command]:
    out: list[Command] = []
    if leader.hex is None or not members:
        return out
    ids = tuple(sorted([leader.id] + [m.id for m in members]))
    remaining = {leader.id: allowance_halves(ctx, state, leader, False) - leader.mf_used}
    for m in members:
        remaining[m.id] = allowance_halves(ctx, state, m, True) - m.mf_used
    for d in range(6):
        dst = geometry.neighbor(*leader.hex, d)
        if dst not in ctx.board or enemy_in_hex(state, leader.player, dst):
            continue
        cost, _ = entry_cost_halves(ctx, leader.hex, dst)
        if cost is None or any(cost > remaining[i] for i in ids):
            continue
        if r06_stacking.rule_6_1_overstacked(state, ctx.types, dst, leader.player, extra_ids=ids):
            if not all(_can_exit_after(ctx, state, state.units[i], dst, remaining[i] - cost) for i in ids):
                continue
        out.append(Command("stack_move", units=ids, hex=dst))
    return out


def legal_pickups_and_drops(ctx: MoveContext, state: State, in_movement: bool) -> list[Command]:
    out: list[Command] = []
    player = state.active
    for u in state.player_units(player):
        if not u.is_infantry or u.hex is None or u.carrier is not None or u.broken:
            continue
        if in_movement and u.prep_fired:
            continue
        if not in_movement and u.move_mode == MOVE_MODE_ADVANCED:
            continue
        for w in state.units_in(u.hex):
            if w.kind != KIND_SW or w.carrier is not None:
                continue
            if pickup_allowed(ctx, state, u, w, in_movement):
                out.append(Command("pickup", units=(u.id,), weapon=w.id))
        for w in state.carried_by(u.id):
            out.append(Command("drop", units=(u.id,), weapon=w.id))
    return out


def capture_allowed(state: State, unit: Unit, weapon: Unit) -> bool:
    """PR-38: where a unit may take a support weapon of the other side.

    Rule 20.84 forbids a capture in a melee hex. A weapon in a hex that holds a
    concealment counter or a hidden unit of its owner is below the counter or on the
    record with that unit, so the other side cannot take it and the legal list does not
    name it (rules 25.2 and 42.1).
    """
    if weapon.player == unit.player:
        return True
    if weapon.hex is None or state.in_melee(weapon.hex):
        return False
    if any(c.hex == weapon.hex and c.player == weapon.player for c in state.concealment):
        return False
    return not any(u.hidden and u.player == weapon.player for u in state.units_in(weapon.hex))


def captured_weapon_kept(ctx: MoveContext, unit: Unit, weapon: Unit) -> bool:
    """PR-38: a captured machine gun changes owner, and other weapons are eliminated.

    Rule 13.5 eliminates a captured weapon that is not a machine gun. Rule 50.4 lets an
    American unit operate each captured weapon.
    """
    if ctx.types[weapon.type_key].weapon_class == WEAPON_CLASS_MG:
        return True
    return ctx.types[unit.type_key].nationality == NATION_OPERATES_ALL_CAPTURED


def pickup_allowed(ctx: MoveContext, state: State, unit: Unit, weapon: Unit, in_movement: bool) -> bool:
    t = ctx.types[weapon.type_key]
    if not capture_allowed(state, unit, weapon):
        return False
    if weapon.player != unit.player and not captured_weapon_kept(ctx, unit, weapon):
        # The capture eliminates the weapon, so no portage test applies to it.
        return True
    leader_cost = t.portage_leader_halves
    if unit.kind == KIND_LEADER:
        if leader_cost is None:
            return False
        if weapon_portage_halves(ctx, state, unit) + leader_cost > LEADER_MAX_PORTAGE * 2:
            return False
    if unit.berserk:
        # Rule 18.43 and QA-18.42: a berserk unit carries only what costs it no factor.
        cost = leader_cost if unit.kind == KIND_LEADER and leader_cost is not None else t.portage_squad_halves
        if weapon_portage_halves(ctx, state, unit) + cost > ctx.types[unit.type_key].free_portage_halves:
            return False
    if in_movement:
        cost = leader_cost if unit.kind == KIND_LEADER and leader_cost is not None else t.portage_squad_halves
        after = weapon_portage_halves(ctx, state, unit) + cost
        excess = after - ctx.types[unit.type_key].free_portage_halves
        allowance = ctx.types[unit.type_key].mf_halves + (LEADER_BONUS_HALVES if in_stack_with_leader(state, unit) else 0) - (excess if excess > 0 else 0)
        if allowance < unit.mf_used:
            return False
    return True


def apply_move(ctx: MoveContext, state: State, command: Command) -> tuple[State, list[Event]]:
    unit = state.units[command.units[0]]
    dst = command.hex
    if dst is None or unit.hex is None:
        raise ValueError("move needs a unit on the board and a destination")
    cost, rules = entry_cost_halves(ctx, unit.hex, dst)
    if cost is None:
        raise ValueError("destination is not passable")
    moved = unit.with_(
        hex=dst,
        moved=True,
        mf_used=unit.mf_used + cost,
        move_mode=MOVE_MODE_SOLO,
        track=unit.track + (dst,),
        portage_max=max(unit.portage_max, weapon_portage(ctx, state, unit)),
    )
    changed = {moved.id: moved}
    for w in state.carried_by(unit.id):
        changed[w.id] = w.with_(hex=dst)
    events = [Event(RULE_5_5, "move", {"unit": unit.id, "from": geometry.hex_id(*unit.hex), "to": geometry.hex_id(*dst), "cost_halves": cost, "rules": list(rules)})]
    return state.with_units(changed), events


def apply_stack_move(ctx: MoveContext, state: State, command: Command) -> tuple[State, list[Event]]:
    dst = command.hex
    units = [state.units[i] for i in command.units]
    leader = [u for u in units if u.kind == KIND_LEADER][0]
    if dst is None or leader.hex is None:
        raise ValueError("stack move needs a destination")
    cost, rules = entry_cost_halves(ctx, leader.hex, dst)
    if cost is None:
        raise ValueError("destination is not passable")
    tag = f"{MOVE_MODE_STACK}{leader.id}"
    changed: dict[int, Unit] = {}
    for u in units:
        changed[u.id] = u.with_(
            hex=dst,
            moved=True,
            mf_used=u.mf_used + cost,
            move_mode=tag,
            track=u.track + (dst,),
            portage_max=max(u.portage_max, weapon_portage(ctx, state, u)),
        )
        for w in state.carried_by(u.id):
            changed[w.id] = w.with_(hex=dst)
    events = [
        Event(
            RULE_5_44,
            "stack_move",
            {"units": list(command.units), "leader": leader.id, "from": geometry.hex_id(*leader.hex), "to": geometry.hex_id(*dst), "cost_halves": cost, "rules": list(rules)},
        )
    ]
    return state.with_units(changed), events


def apply_pickup(ctx: MoveContext, state: State, command: Command) -> tuple[State, list[Event]]:
    unit = state.units[command.units[0]]
    weapon = state.units[command.weapon] if command.weapon is not None else None
    if weapon is None:
        raise ValueError("pickup needs a weapon")
    if weapon.player != unit.player:
        return _capture(ctx, state, unit, weapon)
    picked = weapon.with_(carrier=unit.id, hex=unit.hex)
    return state.with_unit(picked), [Event(RULE_5_7, "pickup", {"unit": unit.id, "weapon": weapon.id})]


def _capture(ctx: MoveContext, state: State, unit: Unit, weapon: Unit) -> tuple[State, list[Event]]:
    """PR-38 with rules 2.7, 13.5, and 50.4: the weapon changes owner or is eliminated."""
    data = {"unit": unit.id, "weapon": weapon.id, "from_player": weapon.player}
    if captured_weapon_kept(ctx, unit, weapon):
        taken = weapon.with_(carrier=unit.id, hex=unit.hex, player=unit.player)
        return state.with_unit(taken), [Event(RULE_13_5, "captured", data)]
    gone = weapon.with_(carrier=None, hex=None, eliminated=True)
    return state.with_unit(gone), [Event(RULE_13_5, "captured_eliminated", data)]


def apply_drop(ctx: MoveContext, state: State, command: Command) -> tuple[State, list[Event]]:
    unit = state.units[command.units[0]]
    weapon = state.units[command.weapon] if command.weapon is not None else None
    if weapon is None:
        raise ValueError("drop needs a weapon")
    dropped = weapon.with_(carrier=None, hex=unit.hex)
    return state.with_unit(dropped), [Event(RULE_5_7, "drop", {"unit": unit.id, "weapon": weapon.id})]


def legal_advances(ctx: MoveContext, state: State) -> list[Command]:
    """Rule 4.7 with the portage limit of rule 5.73."""
    player = state.active
    out: list[Command] = []
    for u in state.player_units(player):
        if not u.is_infantry or u.hex is None or u.carrier is not None or u.broken or u.move_mode == MOVE_MODE_ADVANCED:
            continue
        if state.in_melee(u.hex):
            continue
        if u.berserk:
            # Rule 18.42: a berserk unit advances on its charge, which r18_berserk gives.
            continue
        portage = weapon_portage(ctx, state, u)
        limit = ADVANCE_LEADER_PORTAGE if u.kind == KIND_LEADER else ADVANCE_SQUAD_PORTAGE
        if portage > limit:
            continue
        for d in range(6):
            dst = geometry.neighbor(*u.hex, d)
            if dst not in ctx.board:
                continue
            cost, _ = entry_cost_halves(ctx, u.hex, dst)
            if cost is None:
                continue
            if r06_stacking.rule_6_1_overstacked(state, ctx.types, dst, u.player, extra_ids=(u.id,)):
                continue
            out.append(Command("advance", units=(u.id,), hex=dst))
    out.extend(legal_pickups_and_drops(ctx, state, in_movement=False))
    return out


def apply_advance(ctx: MoveContext, state: State, command: Command) -> tuple[State, list[Event]]:
    unit = state.units[command.units[0]]
    dst = command.hex
    if dst is None or unit.hex is None:
        raise ValueError("advance needs a destination")
    changed = {unit.id: unit.with_(hex=dst, move_mode=MOVE_MODE_ADVANCED)}
    for w in state.carried_by(unit.id):
        changed[w.id] = w.with_(hex=dst)
    return state.with_units(changed), [Event(RULE_4_7, "advance", {"unit": unit.id, "from": geometry.hex_id(*unit.hex), "to": geometry.hex_id(*dst)})]


# ------------------------------------------------------------------ the command handlers (M3)


def bump_into_hidden(ctx: MoveContext, before: State, state: State, command: Command) -> tuple[State, list[Event]]:
    """Rule 42.5: a unit that walks into a hidden unit stops and ends its movement.

    The unit goes back to the hex it came from, and it has no movement factors left. It
    does not put the hidden unit on the board: rule 42.2 does that at the end of the
    Defensive Fire Phase or the Advance Phase, because the unit is next to it now.

    A stack move is the move of each unit of the stack, so each of them stops (PR-32).
    """
    if not command.units or command.hex is None:
        return state, []
    first = before.units[command.units[0]]
    if first.hex is None or not r42_hidden.enemy_hidden_in(before, command.hex, first.player):
        return state, []
    stack = command.action == "stack_move"
    changed: dict[int, Unit] = {}
    events: list[Event] = []
    for uid in command.units:
        mover = before.units[uid]
        if mover.hex is None:
            continue
        bonus = stack and mover.kind != KIND_LEADER
        allowance = allowance_halves(ctx, before, mover, leader_bonus=bonus)
        changed[uid] = state.units[uid].with_(hex=mover.hex, mf_used=allowance, track=mover.track)
        for weapon in state.carried_by(uid):
            changed[weapon.id] = weapon.with_(hex=mover.hex)
        events.append(
            Event(
                r42_hidden.RULE_42_5,
                "stopped",
                {
                    "unit": uid,
                    "hex": geometry.hex_id(*mover.hex),
                    "tried": geometry.hex_id(*command.hex),
                },
            )
        )
    return state.with_units(changed), events


@actions.action("move", unconceals=actions.CAUSE_MOVED)
def _on_move(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    after, events = apply_move(engine.move_ctx, state, command)
    after, ev = bump_into_hidden(engine.move_ctx, state, after, command)
    events.extend(ev)
    return after, events


@actions.action("stack_move", unconceals=actions.CAUSE_MOVED)
def _on_stack_move(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    after, events = apply_stack_move(engine.move_ctx, state, command)
    after, ev = bump_into_hidden(engine.move_ctx, state, after, command)
    events.extend(ev)
    return after, events


# A pickup and a drop are not a move for rules 25.4 and 42.2.
@actions.action("pickup")
def _on_pickup(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    return apply_pickup(engine.move_ctx, state, command)


@actions.action("drop")
def _on_drop(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    return apply_drop(engine.move_ctx, state, command)


@actions.action("advance", unconceals=actions.CAUSE_MOVED)
def _on_advance(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    return apply_advance(engine.move_ctx, state, command)
