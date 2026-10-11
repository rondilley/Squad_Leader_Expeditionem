"""The turn sequence of the engine: the phase state machine and its automatic steps (FR-03).

`run_from` enters a sub-step of a phase, runs each automatic step, and stops at the next
window. Each automatic step has one handler in `AUTO_STEPS`, keyed by the sub-step name
of `slcore.phases`, and each condition of a rare window has one test in `CONDITIONS`.

The two commands of the phase control, `end_setup` and `end_phase`, register here. The
functions take the engine as their first argument and read its static context only.
"""

from __future__ import annotations

from typing import Any, Callable

from slcore import actions, geometry
from slcore.events import Event
from slcore.game import PHASE_DEFENSIVE_FIRE, PHASE_END, PHASE_RALLY, PHASE_ROUT, State
from slcore.phases import (
    AUTO,
    CONDITION_DEMO,
    CONDITION_PUSH,
    CONDITION_SEWER,
    CONDITION_SMOKE,
    PHASE_STEPS,
    SubStep,
    actor_player,
    next_phase,
    sub_step,
)
from slcore.rng import roll_die
from slcore.rules import (
    r13_rout,
    r16_defensive_fire,
    r20_close_combat,
    r23_demolition,
    r24_smoke,
    r25_concealment,
    r27_sewer,
    r34_afv_vs_infantry,
    r35_overrun,
    r42_hidden,
    victory,
)

RULE_4_9 = "4.9"
RULE_PR_12 = "21.2"

# One automatic step: (engine, state, phase, step, events) gives the next state.
AutoStep = Callable[[Any, State, str, SubStep, list[Event]], State]


# ------------------------------------------------------------------ the phase control


@actions.action("end_setup")
def _on_end_setup(engine: Any, state: State, command: Any) -> tuple[State, list[Event]]:
    events: list[Event] = []
    return end_setup(engine, state, events), events


@actions.action("end_phase")
def _on_end_phase(engine: Any, state: State, command: Any) -> tuple[State, list[Event]]:
    events: list[Event] = []
    if state.phase == PHASE_ROUT:
        # PR-36: a rout can take the cover another unit needed. When the side ends its
        # window, rule 13.47 looks again at each of its broken units.
        state, ev = r13_rout.eliminate_hopeless(engine.rout_ctx, engine.types, state, state.active)
        events.extend(ev)
    if sub_step(state.phase, state.sub_step).name == "push_out":
        # Rule 35.8: a unit with no hex to step into is eliminated.
        state, ev = r35_overrun.crush_left(engine.board, state, engine.types, state.active)
        events.extend(ev)
    return run_from(engine, state, state.phase, state.sub_step + 1, events), events


def end_setup(engine: Any, state: State, events: list[Event]) -> State:
    idx = state.setup_index + 1
    events.append(Event("21.2", "setup_done", {"player": state.active}))
    if idx < len(engine.scenario.setup_order):
        player = engine.scenario.side_index(engine.scenario.setup_order[idx])
        return state.with_(setup_index=idx, active=player)
    state, phasing = first_mover(engine, state, events)
    state = state.with_(setup_index=idx, turn=1, phasing=phasing)
    state = victory.update_last_occupant(state, engine.board)
    events.append(Event("4", "turn_start", {"turn": 1, "phasing": phasing}))
    return run_from(engine, state, PHASE_RALLY, 0, events)


def first_mover(engine: Any, state: State, events: list[Event]) -> tuple[State, int]:
    """Project ruling PR-12: the card that says to roll a die gets the core generator.

    Player 0 is the side the scenario names as the first mover. A card with no roll
    gives the first player turn to that side.
    """
    if not engine.scenario.first_mover_roll:
        return state, 0
    rng, die = roll_die(state.rng)
    state = state.with_(rng=rng)
    phasing = 0 if die <= 3 else 1
    events.append(Event(RULE_PR_12, "first_mover", {"die": die, "phasing": phasing}))
    return state, phasing


def run_from(engine: Any, state: State, phase: str, index: int, events: list[Event]) -> State:
    """Enter step `index` of `phase`, run the automatic steps, and stop at the next window."""
    while True:
        steps = PHASE_STEPS[phase]
        if index < len(steps):
            step = steps[index]
            if step.kind == AUTO:
                handler = AUTO_STEPS.get(step.name)
                if handler is None:
                    raise ValueError(f"unknown automatic step {step.name!r} in {phase}")
                state = handler(engine, state, phase, step, events)
                if state.game_over:
                    return state.with_(phase=PHASE_END, sub_step=0)
                index += 1
                continue
            if step.condition and not condition_holds(engine, state, step):
                index += 1
                continue
            return state.with_(phase=phase, sub_step=index, active=actor_player(step, state.phasing))
        state = victory.update_last_occupant(state, engine.board)
        following = next_phase(phase)
        if following is None:
            following = PHASE_RALLY
        events.append(Event("4", "phase", {"phase": following, "turn": state.turn, "phasing": state.phasing}))
        phase = following
        index = 0


# ------------------------------------------------------------------ the automatic steps


def _remove_dm(engine: Any, state: State, phase: str, step: SubStep, events: list[Event]) -> State:
    changed = {u.id: u.with_(dm=False, rally_tried=False) for u in state.units if u.dm or u.rally_tried}
    changed.update({u.id: u.with_(repair_tried=False) for u in state.units if u.repair_tried})
    return state.with_units(changed) if changed else state


def _reset_movement(engine: Any, state: State, phase: str, step: SubStep, events: list[Event]) -> State:
    changed = {}
    for u in state.player_units(state.phasing):
        changed[u.id] = u.with_(mf_used=0, move_mode="", track=(), portage_max=0, mp_used=0)
    return state.with_units(changed)


def _return_units(engine: Any, state: State, phase: str, step: SubStep, events: list[Event]) -> State:
    state, ev = r16_defensive_fire.return_units(state)
    events.extend(ev)
    return state


def _place_prep_fire(engine: Any, state: State, phase: str, step: SubStep, events: list[Event]) -> State:
    """Page 41 step 2.3: the Prep Fire counters go on at the end of the phase.

    Rule 4.3 then stops those units from moving, and rule 4.5 stops them from firing
    again. Within the phase rule 8.4 lets a squad fire a support weapon at a second
    hex, so the marker cannot go on when the first group resolves.
    """
    changed = {}
    # PR-43: a panzerfaust leaves the game when it fires, so the unit carries nothing
    # that shows the shot. The record of the anti-tank shots of the turn does.
    shooters = {firer for firer, _ in state.at_shots}
    for unit in state.units:
        if unit.eliminated or not (unit.is_infantry or unit.is_vehicle):
            continue
        weapons = state.carried_by(unit.id)
        if not unit.fired and not any(w.fired for w in weapons) and unit.id not in shooters:
            continue
        # Rule 33.2 gives the counter to a vehicle as well: a vehicle that fires any
        # weapon in the Prep Fire Phase may not move in the Movement Phase.
        changed[unit.id] = unit.with_(prep_fired=True)
        for w in weapons:
            changed[w.id] = w.with_(prep_fired=True)
    return state.with_units(changed) if changed else state


def _end_fire_phase(engine: Any, state: State, phase: str, step: SubStep, events: list[Event]) -> State:
    state = state.with_(fired_pairs=(), fire_group=None)
    if engine.has_vehicles:
        # Rule 34.8 and PR-44: the crew exposed counter comes off at the end of the
        # next fire phase of the enemy. That is this phase for each vehicle of the
        # side that did not fire in it. The defender fires in the Defensive Fire
        # Phase and the phasing side in the other two.
        firing = 1 - state.phasing if phase == PHASE_DEFENSIVE_FIRE else state.phasing
        state, ev = r34_afv_vs_infantry.clear_exposure(state, 1 - firing)
        events.extend(ev)
        # Rule 35.8 moves the infantry below a vehicle in the window that follows
        # the Defensive Fire Phase (PR-51).
    return state


def _resolve_overruns(engine: Any, state: State, phase: str, step: SubStep, events: list[Event]) -> State:
    """PR-54 and rule 35.6: each overrun the phasing side declared in the Movement Phase
    resolves now, after the defensive fire, for each vehicle that survived it."""
    if not engine.has_vehicles:
        return state
    state, ev = r35_overrun.resolve_pending(engine.armor_ctx, engine.fire_ctx, state, state.phasing)
    events.extend(ev)
    return state


def _expire_smoke(engine: Any, state: State, phase: str, step: SubStep, events: list[Event]) -> State:
    state, ev = r24_smoke.expire(state, state.phasing)
    events.extend(ev)
    changed = {u.id: u.with_(made_smoke=False) for u in state.player_units(state.phasing) if u.made_smoke}
    return state.with_units(changed) if changed else state


def _arm_demo(engine: Any, state: State, phase: str, step: SubStep, events: list[Event]) -> State:
    state, ev = r23_demolition.arm(state)
    events.extend(ev)
    return state


def _concealment_adjacency(engine: Any, state: State, phase: str, step: SubStep, events: list[Event]) -> State:
    state, ev = r25_concealment.refresh_adjacency(state)
    events.extend(ev)
    # Rule 42.2 names the same two phases: a hidden unit next to an enemy unit comes on
    # the board at the end of a Defensive Fire Phase or an Advance Phase.
    state, ev = r42_hidden.refresh_adjacency(state, engine.board)
    events.extend(ev)
    return state


def _conceal_grow(engine: Any, state: State, phase: str, step: SubStep, events: list[Event]) -> State:
    state, ev = r25_concealment.grow(state, engine.board)
    events.extend(ev)
    return state


def _sewer_conceal_step(engine: Any, state: State, phase: str, step: SubStep, events: list[Event]) -> State:
    return sewer_conceal(engine, state, events)


def _clear_tracks(engine: Any, state: State, phase: str, step: SubStep, events: list[Event]) -> State:
    changed = {u.id: u.with_(track=()) for u in state.units if u.track}
    return state.with_units(changed) if changed else state


def _remove_prep_fire(engine: Any, state: State, phase: str, step: SubStep, events: list[Event]) -> State:
    changed = {u.id: u.with_(prep_fired=False) for u in state.units if u.prep_fired}
    return state.with_units(changed) if changed else state


def _rout_check(engine: Any, state: State, phase: str, step: SubStep, events: list[Event]) -> State:
    player = actor_player(step, state.phasing)
    state, ev = r13_rout.eliminate_hopeless(engine.rout_ctx, engine.types, state, player)
    events.extend(ev)
    return state


def _rout_cleanup(engine: Any, state: State, phase: str, step: SubStep, events: list[Event]) -> State:
    state, ev = r13_rout.eliminate_overstacked_broken(engine.rout_ctx, engine.types, state)
    events.extend(ev)
    changed = {u.id: u.with_(stay=False, routed=False) for u in state.units if u.stay or u.routed}
    return state.with_units(changed) if changed else state


def _cc_resolve(engine: Any, state: State, phase: str, step: SubStep, events: list[Event]) -> State:
    # An empty declaration list still runs rules 20.9 and 20.71. A broken squad leaves the
    # hex, and a leader with no squad left goes with it.
    state, ev = r20_close_combat.resolve(state, engine.types, engine.tables.cc)
    events.extend(ev)
    return check_sudden_death(engine, state, events)


def _end_player_turn(engine: Any, state: State, phase: str, step: SubStep, events: list[Event]) -> State:
    changed = {}
    for u in state.units:
        if u.moved or u.mf_used or u.move_mode or u.track or u.portage_max or u.stay or u.fired or u.directed or u.manned_mg or u.sewer_move or u.demo_placed or u.made_smoke:
            changed[u.id] = u.with_(
                moved=False,
                mf_used=0,
                move_mode="",
                track=(),
                portage_max=0,
                stay=False,
                fired=False,
                directed=False,
                manned_mg=False,
                sewer_move=False,
                demo_placed=False,
                made_smoke=False,
            )
    if engine.has_vehicles:
        # Rules 30.2, 33.2, 34.7, 35.8, and 31.3: what a vehicle carries into the next
        # player turn is its facing and its damage, and nothing else.
        for u in state.units:
            if not u.is_vehicle:
                continue
            if u.mp_used or u.pivoted or u.gun_shots or u.mg_fired or u.overran or u.boarded:
                base = changed.get(u.id, u)
                changed[u.id] = base.with_(
                    mp_used=0, pivoted=False, gun_shots=0, mg_fired=False, overran=False, boarded=False
                )
    state = state.with_units(changed) if changed else state
    state = state.with_(at_shots=())
    state = victory.update_last_occupant(state, engine.board)
    phasing = 1 - state.phasing
    turn = state.turn
    if phasing == 0:
        turn += 1
    events.append(Event(RULE_4_9, "player_turn_end", {"turn": state.turn, "next_phasing": phasing, "next_turn": turn}))
    if turn > state.turn_limit:
        return finish(engine, state.with_(phasing=phasing, turn=turn), events, "the last turn is complete")
    return state.with_(phasing=phasing, turn=turn)


# The handler of each automatic sub-step of `slcore.phases.PHASE_STEPS`, by its name.
AUTO_STEPS: dict[str, AutoStep] = {
    "remove_dm": _remove_dm,
    "reset_movement": _reset_movement,
    "return_units": _return_units,
    "place_prep_fire": _place_prep_fire,
    "end_fire_phase": _end_fire_phase,
    "resolve_overruns": _resolve_overruns,
    "expire_smoke": _expire_smoke,
    "arm_demo": _arm_demo,
    "concealment_adjacency": _concealment_adjacency,
    "conceal_grow": _conceal_grow,
    "sewer_conceal": _sewer_conceal_step,
    "clear_tracks": _clear_tracks,
    "remove_prep_fire": _remove_prep_fire,
    "rout_check": _rout_check,
    "rout_cleanup": _rout_cleanup,
    "cc_resolve": _cc_resolve,
    "end_player_turn": _end_player_turn,
}


# ------------------------------------------------------------------ the rare windows


def _smoke_ready(engine: Any, state: State, player: int) -> bool:
    return any(r24_smoke.can_place(state, engine.types, u) for u in state.player_units(player))


def _demo_ready(engine: Any, state: State, player: int) -> bool:
    return bool(r23_demolition.ready(state, player))


def _sewer_lost(engine: Any, state: State, player: int) -> bool:
    return r27_sewer.lost_party(state) is not None


def _push_out(engine: Any, state: State, player: int) -> bool:
    return engine.has_vehicles and bool(r35_overrun.pushed_units(state, player))


# A rare window opens only when its rule has a decision for the player.
CONDITIONS: dict[str, Callable[[Any, State, int], bool]] = {
    CONDITION_SMOKE: _smoke_ready,
    CONDITION_DEMO: _demo_ready,
    CONDITION_SEWER: _sewer_lost,
    CONDITION_PUSH: _push_out,
}


def condition_holds(engine: Any, state: State, step: SubStep) -> bool:
    test = CONDITIONS.get(step.condition)
    if test is None:
        raise ValueError(f"unknown sub-step condition {step.condition!r}")
    return test(engine, state, actor_player(step, state.phasing))


# ------------------------------------------------------------------ shared steps


def sewer_conceal(engine: Any, state: State, events: list[Event]) -> State:
    """Rule 27.5: a stack that came up with no enemy next to it in the building is covered."""
    for unit in r27_sewer.arrivals(state, state.phasing):
        if unit.hex is None:
            continue
        if r27_sewer.same_building_enemy(engine.board, state, unit.hex, unit.player):
            continue
        if any(u.player == unit.player and u.is_infantry and not u.sewer_move for u in state.units_in(unit.hex)):
            # Rule 25.41: a unit that came into the hex in view stays in view. A counter
            # covers each unit of its hex, so the hex of such a unit gets no counter.
            continue
        if any(c.hex == unit.hex and c.player == unit.player for c in state.concealment):
            continue
        state, counter = r25_concealment.add(state, unit.player, unit.hex)
        events.append(
            Event(
                r27_sewer.RULE_27_5,
                "concealed",
                {"counter": counter.id, "player": unit.player, "hex": geometry.hex_id(*unit.hex)},
            )
        )
    return state


def check_sudden_death(engine: Any, state: State, events: list[Event]) -> State:
    """A side with no infantry counter left cannot play on, so the game ends."""
    for player in (0, 1):
        alive = [u for u in state.player_units(player) if u.hex is not None or u.carrier is not None]
        if any(u.is_infantry for u in alive):
            continue
        if any(u.is_vehicle and not u.wreck for u in alive):
            continue
        return finish(engine, state, events, f"player {player} has no unit left that can fight")
    return state


def finish(engine: Any, state: State, events: list[Event], cause: str) -> State:
    state = victory.update_last_occupant(state, engine.board)
    if not engine.scenario.victory:
        events.append(Event(RULE_4_9, "game_end", {"result": "no_result", "cause": cause}))
        return state.with_(game_over=True, result="no_result", result_cause=cause)
    winner, why, results = victory.evaluate(state, engine.board, engine.scenario, engine.types)
    events.append(
        Event(
            victory.RULE_VICTORY,
            "game_end",
            {"result": winner, "cause": f"{cause}: {why}", "conditions": [r.to_dict() for r in results]},
        )
    )
    return state.with_(game_over=True, result=winner, result_cause=f"{cause}: {why}")
