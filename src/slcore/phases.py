"""The phase state machine (FR-03, ARCHITECTURE section 3.2).

Each phase is a sequence of sub-steps. A window sub-step opens a command window for
one player. An automatic sub-step changes the state and emits events.

A sub-step with a condition is a window that opens only when the rule has something to
decide. Smoke, a demolition charge, and a lost sewer stack are rare, and a window that
is always open would put an empty decision in every player turn.
"""

from __future__ import annotations

from dataclasses import dataclass

from slcore.game import (
    PHASE_ADVANCE,
    PHASE_ADVANCING_FIRE,
    PHASE_CLOSE_COMBAT,
    PHASE_DEFENSIVE_FIRE,
    PHASE_MOVEMENT,
    PHASE_PREP_FIRE,
    PHASE_RALLY,
    PHASE_ROUT,
    PHASE_SETUP,
    PLAYER_TURN_PHASES,
)

WINDOW = "window"
AUTO = "auto"

ACTOR_PHASING = "phasing"
ACTOR_DEFENDER = "defender"
ACTOR_SETUP = "setup"
ACTOR_NONE = ""

CONDITION_SMOKE = "smoke_ready"
CONDITION_DEMO = "demo_ready"
CONDITION_SEWER = "sewer_lost"
CONDITION_PUSH = "push_out"


@dataclass(frozen=True)
class SubStep:
    name: str
    kind: str
    actor: str
    rule_id: str
    condition: str = ""


PHASE_STEPS: dict[str, tuple[SubStep, ...]] = {
    PHASE_SETUP: (
        SubStep("place", WINDOW, ACTOR_SETUP, "21.2"),
    ),
    PHASE_RALLY: (
        SubStep("rally_window", WINDOW, ACTOR_PHASING, "4.1"),
        SubStep("rally_window", WINDOW, ACTOR_DEFENDER, "4.1"),
        SubStep("remove_dm", AUTO, ACTOR_NONE, "14.6"),
    ),
    PHASE_PREP_FIRE: (
        SubStep("expire_smoke", AUTO, ACTOR_NONE, "24.8"),
        SubStep("smoke_window", WINDOW, ACTOR_PHASING, "24.3", CONDITION_SMOKE),
        SubStep("fire_window", WINDOW, ACTOR_PHASING, "4.2"),
        SubStep("place_prep_fire", AUTO, ACTOR_NONE, "4.2"),
        SubStep("end_fire_phase", AUTO, ACTOR_NONE, "8.5"),
    ),
    PHASE_MOVEMENT: (
        SubStep("reset_movement", AUTO, ACTOR_NONE, "5.2"),
        SubStep("sewer_return", WINDOW, ACTOR_DEFENDER, "27.22", CONDITION_SEWER),
        SubStep("move_window", WINDOW, ACTOR_PHASING, "4.3"),
        SubStep("sewer_conceal", AUTO, ACTOR_NONE, "27.5"),
    ),
    PHASE_DEFENSIVE_FIRE: (
        SubStep("fire_window", WINDOW, ACTOR_DEFENDER, "4.4"),
        SubStep("return_units", AUTO, ACTOR_NONE, "16.3"),
        SubStep("arm_demo", AUTO, ACTOR_NONE, "23.3"),
        SubStep("end_fire_phase", AUTO, ACTOR_NONE, "8.5"),
<<<<<<< Updated upstream
=======
        # PR-54 and rule 35.6: the overruns of the Movement Phase resolve after the fire.
        SubStep("resolve_overruns", AUTO, ACTOR_NONE, "35.6"),
>>>>>>> Stashed changes
        # Rule 35.8 and PR-51: the infantry below an enemy vehicle steps to one side.
        SubStep("push_out", WINDOW, ACTOR_DEFENDER, "35.8", CONDITION_PUSH),
        SubStep("clear_tracks", AUTO, ACTOR_NONE, "16.3"),
        SubStep("concealment_adjacency", AUTO, ACTOR_NONE, "25.4"),
    ),
    PHASE_ADVANCING_FIRE: (
        SubStep("demo_window", WINDOW, ACTOR_PHASING, "23.4", CONDITION_DEMO),
        SubStep("fire_window", WINDOW, ACTOR_PHASING, "4.5"),
        SubStep("end_fire_phase", AUTO, ACTOR_NONE, "8.5"),
        SubStep("remove_prep_fire", AUTO, ACTOR_NONE, "4.5"),
    ),
    PHASE_ROUT: (
        SubStep("rout_check", AUTO, ACTOR_PHASING, "13.47"),
        SubStep("rout_window", WINDOW, ACTOR_PHASING, "4.6"),
        SubStep("rout_check", AUTO, ACTOR_DEFENDER, "13.47"),
        SubStep("rout_window", WINDOW, ACTOR_DEFENDER, "4.6"),
        SubStep("rout_cleanup", AUTO, ACTOR_NONE, "13.44"),
    ),
    PHASE_ADVANCE: (
        SubStep("advance_window", WINDOW, ACTOR_PHASING, "4.7"),
        SubStep("concealment_adjacency", AUTO, ACTOR_NONE, "25.4"),
    ),
    PHASE_CLOSE_COMBAT: (
        SubStep("cc_declare", WINDOW, ACTOR_PHASING, "20.4"),
        SubStep("cc_declare", WINDOW, ACTOR_DEFENDER, "20.4"),
        SubStep("cc_resolve", AUTO, ACTOR_NONE, "20.2"),
        SubStep("conceal_grow", AUTO, ACTOR_NONE, "25.3"),
        SubStep("end_player_turn", AUTO, ACTOR_NONE, "4.9"),
    ),
}

FIRE_PHASES = (PHASE_PREP_FIRE, PHASE_DEFENSIVE_FIRE, PHASE_ADVANCING_FIRE)
FIRE_WINDOW = "fire_window"


def sub_step(phase: str, index: int) -> SubStep:
    return PHASE_STEPS[phase][index]


def next_phase(phase: str) -> str | None:
    """The phase after this one in a player turn, or None after Close Combat."""
    if phase == PHASE_SETUP:
        return PLAYER_TURN_PHASES[0]
    i = PLAYER_TURN_PHASES.index(phase)
    if i + 1 < len(PLAYER_TURN_PHASES):
        return PLAYER_TURN_PHASES[i + 1]
    return None


def actor_player(step: SubStep, phasing: int) -> int:
    if step.actor == ACTOR_DEFENDER:
        return 1 - phasing
    return phasing


def fire_rule(phase: str) -> str:
    """Which firing restriction applies in this phase (rules 4.2, 4.4, 4.5)."""
    if phase == PHASE_PREP_FIRE:
        return "prep"
    if phase == PHASE_ADVANCING_FIRE:
        return "advancing"
    return "defensive"
