"""Shared pytest configuration for the whole suite (B6, B9).

The default run collects about 1,500 tests and runs for about ten minutes. The tests in
SLOW_TESTS took 3 s or more each in a measurement of the whole suite with
`pytest --durations=0` on 2026-09-23 (Linux, 24 cores). Together they take about 430 s
of the 590 s. This file gives each of them the `slow` marker, so the test files of the
other areas do not change.

The quick run, about three minutes:

    python -m pytest -m "not slow and not gate and not integration"

A test module that imports an optional library at its top, with no skip of its own, is
in REQUIRES. On an install with no such library, the module is left out of the
collection, and the end of the report names it and the library (B6). Then a report of a
run on the base install says which parts did not run.

The full run is `python -m pytest` (the default `addopts` leaves out `gate` and
`integration`). A test that becomes slow goes in this list, or it gets
`@pytest.mark.slow` in its own file. Measure again with `--durations=0`.
"""

from __future__ import annotations

import importlib.util

import pytest

SLOW_TESTS = frozenset(
    {
        "tests/agents/test_ppo_smoke.py::test_a_short_training_run_gives_a_finite_loss_and_a_rate",
        "tests/agents/test_ppo_smoke.py::test_the_evaluation_gives_a_win_rate_with_an_interval",
        "tests/agents/test_scripted.py::test_a_wider_charge_range_places_more_charges",
        "tests/agents/test_scripted.py::test_each_agent_plays_one_game_of_each_scenario[s01_guards_counterattack]",
        "tests/agents/test_scripted.py::test_each_agent_plays_one_game_of_each_scenario[s04_armor_probe]",
        "tests/agents/test_scripted.py::test_the_engineer_uses_the_rules_that_the_others_do_not",
        "tests/agents/test_scripted.py::test_the_gate_run_reports_each_pair_and_its_parameters",
        "tests/agents/test_traces.py::test_a_record_holds_each_field_that_the_data_requirement_names",
        "tests/agents/test_v6_tempo.py::test_the_attacker_moves_after_turn_one",
        "tests/agents/test_v7_doctrine.py::test_a_high_floor_places_no_smoke",
        "tests/agents/test_v7_doctrine.py::test_the_smoke_of_v7_is_measured_in_a_game",
        "tests/agents/test_v7_doctrine.py::test_v7_gives_a_legal_command_in_each_frame_of_a_game",
        "tests/agents/test_v7_doctrine.py::test_v7_places_the_smoke_where_it_takes_the_loss_off_its_force",
        "tests/agents/test_v7_doctrine.py::test_v7_plays_a_full_game_and_replays",
        "tests/agents/test_workers.py::test_a_pool_collects_the_steps_of_each_worker_with_their_rewards_and_ends",
        "tests/agents/test_workers.py::test_the_imitation_pool_gives_the_same_games_as_one_process",
        "tests/armor/test_armor_game.py::test_a_random_game_reaches_the_armor_rules",
        "tests/armor/test_armor_game.py::test_a_vehicle_never_ends_the_movement_phase_on_another_vehicle",
        "tests/armor/test_armor_game.py::test_the_armor_scenario_plays_to_the_end_and_replays",
        "tests/armor/test_tanker_agent.py::test_a_game_between_two_tankers_plays_and_replays",
        "tests/armor/test_tanker_agent.py::test_the_engineer_leaves_the_tanks_where_they_stand",
        "tests/armor/test_tanker_agent.py::test_the_tanker_drives_and_fires",
        "tests/artifact/test_audit_release.py::test_this_repository_holds_nothing_that_must_not_leave_the_machine",
        "tests/boards/test_composition.py::test_a_game_on_a_composition_replays",
        "tests/boards/test_geomorphic.py::test_one_thousand_seeds_satisfy_the_edge_rules",
        "tests/boards/test_zone_setup.py::test_two_hundred_seeds_set_up_scenario_one_with_no_error",
        "tests/browser/test_computer_vs_computer.py::test_two_computer_opponents_play_a_whole_game_in_the_browser",
        "tests/browser/test_play_ui.py::test_a_person_plays_by_the_board_with_the_keys_and_the_helper",
        "tests/browser/test_play_ui.py::test_a_terminal_error_stops_the_reconnect",
        "tests/engine/test_scenarios_2_and_3a.py::test_scenario_three_a_plays_the_whole_board_and_replays",
        "tests/engine/test_scenarios_2_and_3a.py::test_scenario_three_a_reaches_the_sewers",
        "tests/engine/test_scenarios_2_and_3a.py::test_scenario_two_plays_to_the_end_and_replays",
        "tests/engine/test_scenarios_2_and_3a.py::test_the_first_mover_comes_from_the_die",
        "tests/engine/test_scenarios_2_and_3a.py::test_the_new_rules_of_scenario_two_reach_a_game",
        "tests/host/test_protocol_v2.py::test_the_idle_seat_never_gets_the_state_hash",
        "tests/lan/test_two_clients.py::test_the_time_from_one_client_to_the_other_is_inside_the_budget",
        "tests/lan/test_two_clients.py::test_two_clients_take_one_seat_each_and_play_a_turn",
        "tests/secrecy/test_core_property.py::test_no_seat_sees_a_secret_unit_in_its_list_or_its_view[s00b_combined_forces]",
        "tests/secrecy/test_core_property.py::test_no_seat_sees_a_secret_unit_in_its_list_or_its_view[s00c_two_board_advance]",
        "tests/secrecy/test_core_property.py::test_no_seat_sees_a_secret_unit_in_its_list_or_its_view[s02_tractor_works]",
        "tests/secrecy/test_core_property.py::test_no_seat_sees_a_secret_unit_in_its_list_or_its_view[s03a_streets_of_stalingrad]",
        "tests/secrecy/test_core_property.py::test_no_seat_sees_a_secret_unit_in_its_list_or_its_view[s04_armor_probe]",
        "tests/secrecy/test_views.py::test_a_view_never_names_a_unit_below_an_opposing_counter",
        "tests/window3d/test_play3d.py::test_a_person_plays_against_the_computer_in_3d",
        "tests/window/test_window_plays_a_game.py::test_the_game_moves_on_while_the_window_watches",
        "tests/window/test_window_play_v2.py::test_the_panel_shows_the_result_the_conditions_and_the_losses_at_the_end",
    }
)


# Whole modules that came after the measurement. None at this time: a new module marks its
# own long tests with @pytest.mark.slow.
SLOW_PREFIXES: tuple[str, ...] = ()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if item.nodeid in SLOW_TESTS or item.nodeid.startswith(SLOW_PREFIXES):
            item.add_marker(pytest.mark.slow)
        gone = _missing(REQUIRES_TESTS.get(item.nodeid, ()))
        if gone:
            item.add_marker(pytest.mark.skip(reason=f"needs {', '.join(gone)}, an optional extra"))


# The test modules that import an optional library at their top, and the libraries.
REQUIRES: dict[str, tuple[str, ...]] = {
    "agents/test_learned_agent.py": ("numpy",),
    "agents/test_reward.py": ("numpy",),
    "cards/test_scenario_card.py": ("pygame",),
    "shape/test_shape.py": ("numpy",),
}


def _missing(libraries: tuple[str, ...]) -> list[str]:
    return [name for name in libraries if importlib.util.find_spec(name) is None]


LEFT_OUT: dict[str, list[str]] = {}
for _module, _libraries in REQUIRES.items():
    _gone = _missing(_libraries)
    if _gone:
        LEFT_OUT[_module] = _gone

collect_ignore = sorted(LEFT_OUT)

# Single tests of a module that runs on the base install, where the one test reads an
# optional library. The test gets a skip that names the library.
REQUIRES_TESTS: dict[str, tuple[str, ...]] = {
    "tests/browser/test_render_constants.py::test_the_browser_and_the_window_print_the_counter_face_from_one_layout": (
        "pygame",
    ),
}


def pytest_terminal_summary(terminalreporter, exitstatus: int, config: pytest.Config) -> None:
    if not LEFT_OUT:
        return
    terminalreporter.section("left out: an optional extra is not installed")
    for module, libraries in sorted(LEFT_OUT.items()):
        terminalreporter.write_line(f"tests/{module}: needs {', '.join(libraries)}")
