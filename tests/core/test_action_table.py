"""The tables of the handlers hold each action and each sub-step of the turn (M3, PR-34).

The engine finds the handler of a command, the generator of a window, the handler of an
automatic step, and the test of a rare window in four tables. A name that has no entry is
a command the core cannot apply or a step it cannot run, so each check below is a
complete match of a table to the names of `slcore.commands` and `slcore.phases`.
"""

from __future__ import annotations

from slcore import actions, commands, turn
from slcore.phases import AUTO, PHASE_STEPS, WINDOW


def _steps(kind: str) -> set[str]:
    return {step.name for steps in PHASE_STEPS.values() for step in steps if step.kind == kind}


def test_each_action_has_one_handler_and_no_handler_is_extra():
    assert set(actions.ACTION_SPECS) == set(commands.ACTIONS)
    assert len(commands.ACTIONS) == len(set(commands.ACTIONS))


def test_each_handler_is_the_record_of_its_own_name():
    for name, spec in actions.ACTION_SPECS.items():
        assert spec.name == name
        assert callable(spec.apply)
        assert spec.module.startswith("slcore."), f"{name} is registered outside the core: {spec.module}"


def test_the_unconcealing_table_is_the_actions_with_an_act():
    acts = {name for name, spec in actions.ACTION_SPECS.items() if spec.unconceals}
    assert set(actions.UNCONCEALING) == acts
    assert {"move", "group_fire"} <= acts


def test_each_window_sub_step_has_a_generator():
    assert _steps(WINDOW) == set(actions.WINDOWS)


def test_each_automatic_sub_step_has_a_handler():
    missing = _steps(AUTO) - set(turn.AUTO_STEPS)
    assert not missing, f"automatic steps with no handler: {sorted(missing)}"


def test_each_condition_of_a_rare_window_has_a_test():
    conditions = {step.condition for steps in PHASE_STEPS.values() for step in steps if step.condition}
    assert conditions == set(turn.CONDITIONS)
