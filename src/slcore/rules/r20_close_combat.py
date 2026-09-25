"""Rule 20, close combat."""

from __future__ import annotations

from itertools import combinations
from typing import Mapping

from slcore import actions, geometry
from slcore.commands import Command
from slcore.events import Event
from slcore.game import CcDeclaration, State
from slcore.geometry import HexRef
from slcore.rng import roll_2d6
from slcore.rules import r12_morale
from slcore.tabledata import CcTable
from slcore.units import KIND_LEADER, KIND_SW, Unit, UnitType

RULE_20_1 = "20.1"
RULE_20_2 = "20.2"
RULE_20_3 = "20.3"
RULE_20_4 = "20.4"
RULE_20_5 = "20.5"
RULE_20_6 = "20.6"
RULE_20_7 = "20.7"
RULE_20_71 = "20.71"
RULE_20_8 = "20.8"
RULE_20_9 = "20.9"

LEADER_NOMINAL_FIREPOWER = 1


def contested_hexes(state: State) -> list[HexRef]:
    out = []
    for h in sorted({u.hex for u in state.units if u.hex is not None and u.carrier is None and not u.eliminated}):
        players = {u.player for u in state.infantry_in(h)}
        if len(players) > 1:
            out.append(h)
    return out


def eligible(state: State, hex_ref: HexRef, player: int) -> list[Unit]:
    return sorted((u for u in state.infantry_in(hex_ref) if u.player == player and not u.broken), key=lambda u: u.id)


def targets_in(state: State, hex_ref: HexRef, player: int) -> list[Unit]:
    """Rule 20.7: a leader is a target only when it began the phase alone in the hex."""
    enemies = sorted((u for u in state.infantry_in(hex_ref) if u.player != player), key=lambda u: u.id)
    squads = [u for u in enemies if u.kind != KIND_LEADER]
    if squads:
        return squads
    return enemies


def already_attacked(state: State, unit_id: int) -> bool:
    return any(unit_id in d.attackers for d in state.cc_declarations)


def legal_declarations(state: State, types: Mapping[str, UnitType], player: int) -> list[Command]:
    """Rule 20.4: the attacks may be divided in any way, and each unit attacks one time.

    PR-08: an attacker group is any set of the eligible units of the hex. Rule 6.1 keeps
    that set to four units. A group with no attack firepower has no odds (rules 20.3 and
    20.72), so it is not a declaration.
    """
    out: list[Command] = []
    for h in contested_hexes(state):
        attackers = [u for u in eligible(state, h, player) if not already_attacked(state, u.id)]
        targets = targets_in(state, h, player)
        if not attackers or not targets:
            continue
        used = {d.leader for d in state.cc_declarations if d.leader is not None}
        leaders = [u.id for u in attackers if u.kind == KIND_LEADER and not u.directed and u.id not in used]
        target_sets = [(t.id,) for t in targets]
        if len(targets) > 1:
            target_sets.append(tuple(t.id for t in targets))
        for size in range(1, len(attackers) + 1):
            for group in combinations([u.id for u in attackers], size):
                if firepower(state, types, group, attacking=True) <= 0:
                    continue
                for tgroup in target_sets:
                    out.append(Command("cc_attack", units=tuple(group), extra=(("targets", tuple(tgroup)),)))
                    for leader in leaders:
                        if leader in group:
                            out.append(Command("cc_attack", units=tuple(group), extra=(("leader", leader), ("targets", tuple(tgroup)))))
    return out


def apply_declaration(state: State, command: Command, player: int) -> tuple[State, list[Event]]:
    extra = dict(command.extra)
    targets = tuple(int(x) for x in extra.get("targets", ()))
    leader = extra.get("leader")
    declaration = CcDeclaration(player, tuple(command.units), targets, None if leader is None else int(leader))
    state = state.with_(cc_declarations=state.cc_declarations + (declaration,))
    return state, [Event(RULE_20_4, "cc_declare", {"player": player, "attackers": list(command.units), "targets": list(targets), "leader": leader})]


def firepower(state: State, types: Mapping[str, UnitType], unit_ids: tuple[int, ...], attacking: bool) -> int:
    """Rules 20.5 and 20.72: light machine guns add to the attack, and a lone leader has 1 factor."""
    total = 0
    for uid in unit_ids:
        unit = state.units[uid]
        if unit.eliminated:
            continue
        fp = types[unit.type_key].firepower
        if unit.kind == KIND_LEADER:
            fp = LEADER_NOMINAL_FIREPOWER if alone_leader(state, unit) else 0
        total += fp
        if attacking:
            for w in state.carried_by(uid):
                if w.type_key.endswith(":LMG") and not w.malfunction:
                    total += types[w.type_key].firepower
    return total


def alone_leader(state: State, unit: Unit) -> bool:
    if unit.kind != KIND_LEADER or unit.hex is None:
        return False
    return not any(u.player == unit.player and u.kind != KIND_LEADER for u in state.infantry_in(unit.hex))


def resolve(state: State, types: Mapping[str, UnitType], table: CcTable) -> tuple[State, list[Event]]:
    """Rules 20.2 and 20.3: each declared attack rolls, and the effects apply at the same time."""
    events: list[Event] = []
    eliminated: set[int] = set()
    hexes_before = {h: {u.id for u in state.infantry_in(h)} for h in contested_hexes(state)}
    for declaration in state.cc_declarations:
        attack = firepower(state, types, declaration.attackers, attacking=True)
        defense = firepower(state, types, declaration.targets, attacking=False)
        row = table.odds_row(attack, defense)
        if attack <= 0:
            # Rule 20.3: an attack with no firepower has no odds and no roll.
            events.append(
                Event(
                    RULE_20_3,
                    "cc_no_attack",
                    {"player": declaration.player, "attackers": list(declaration.attackers), "targets": list(declaration.targets)},
                )
            )
            continue
        rng, dice = roll_2d6(state.rng)
        state = state.with_(rng=rng)
        raw = dice[0] + dice[1]
        modifier = types[state.units[declaration.leader].type_key].leadership if declaration.leader is not None else 0
        adjusted = raw + modifier
        data = {
            "player": declaration.player,
            # The leader whose modifier applied, so that the log and the campaign scorer
            # of rule 4.1B can say who led the attack.
            "leader": declaration.leader,
            "attackers": list(declaration.attackers),
            "targets": list(declaration.targets),
            "attack": attack,
            "defense": defense,
            "odds": row.label,
            "kill": row.kill,
            "dice": list(dice),
            "leadership": modifier,
            "adjusted": adjusted,
        }
        if adjusted <= row.kill:
            eliminated.update(declaration.targets)
            events.append(Event(RULE_20_3, "cc_kill", data))
        else:
            events.append(Event(RULE_20_3, "cc_miss", data))
    for uid in sorted(eliminated):
        unit = state.units[uid]
        if unit.eliminated:
            continue
        # Rule 13.5: drop while the carrier still has its hex.
        state, drop = r12_morale.drop_weapons(state, uid)
        events.extend(drop)
    changed = {}
    for uid in sorted(eliminated):
        unit = state.units[uid]
        if unit.eliminated:
            continue
        changed[uid] = unit.with_(eliminated=True, hex=None, carrier=None)
    if changed:
        state = state.with_units(changed)
    # Rule 20.9 removes a broken squad before rule 20.71 looks for a squad left in the hex.
    state, ev = broken_in_melee(state)
    events.extend(ev)
    state, ev = leaders_without_squads(state, hexes_before)
    events.extend(ev)
    state, ev = update_melee(state)
    events.extend(ev)
    return state.with_(cc_declarations=()), events


def leaders_without_squads(state: State, hexes_before: dict[HexRef, set[int]]) -> tuple[State, list[Event]]:
    """Rule 20.71: leaders go with the last friendly squad in the hex."""
    events: list[Event] = []
    for hex_ref, ids in hexes_before.items():
        for player in (0, 1):
            squads = [i for i in ids if state.units[i].player == player and state.units[i].kind != KIND_LEADER]
            if not squads or any(not state.units[i].eliminated for i in squads):
                continue
            for i in sorted(ids):
                unit = state.units[i]
                if unit.player == player and unit.kind == KIND_LEADER and not unit.eliminated:
                    # Rule 13.5: the weapon falls in the hex while the leader still has it.
                    state, drop = r12_morale.drop_weapons(state, i)
                    events.extend(drop)
                    state = state.with_unit(state.units[i].with_(eliminated=True, hex=None, carrier=None))
                    events.append(Event(RULE_20_71, "eliminated", {"unit": i, "cause": "no friendly squad in the close combat hex"}))
    return state, events


def broken_in_melee(state: State) -> tuple[State, list[Event]]:
    """Rule 20.9: a broken unit in a melee hex is eliminated."""
    events: list[Event] = []
    changed = {}
    for h in contested_hexes(state):
        for u in state.infantry_in(h):
            if u.broken and not u.eliminated:
                changed[u.id] = u.with_(eliminated=True, hex=None, carrier=None)
                events.append(Event(RULE_20_9, "eliminated", {"unit": u.id, "cause": "broken in a melee hex"}))
    if changed:
        state = state.with_units(changed)
    return state, events


def update_melee(state: State) -> tuple[State, list[Event]]:
    """Rule 20.8: the units that remain in a contested hex are locked in melee."""
    melee = tuple(contested_hexes(state))
    events: list[Event] = []
    for h in melee:
        if h not in state.melee:
            events.append(Event(RULE_20_8, "melee", {"hex": geometry.hex_id(*h)}))
    return state.with_(melee=melee), events


# ------------------------------------------------------------------ the command handler (M3)
# The hex of a close combat is contested, so rule 25.4 has taken each counter already.


@actions.action("cc_attack")
def _on_cc_attack(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    return apply_declaration(state, command, state.active)
