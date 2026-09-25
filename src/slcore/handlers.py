"""The modules that register a handler in `slcore.actions` (M3).

An import of this module imports each of them, so the tables of `slcore.actions` are
complete. A new module that registers a handler goes in this list.
"""

from __future__ import annotations

from slcore import fire_window, turn, windows  # noqa: F401
from slcore.rules import (  # noqa: F401
    r05_movement,
    r08_fire,
    r10_resolution,
    r13_rout,
    r14_rally,
    r16_defensive_fire,
    r20_close_combat,
    r21_setup,
    r23_demolition,
    r24_smoke,
    r25_concealment,
    r27_sewer,
    r30_vehicle_movement,
    r31_transport,
    r34_afv_vs_infantry,
    r35_overrun,
    r36_infantry_vs_afv,
    r37_at_weapons,
    r38_fate,
)

MODULES = (
    fire_window,
    turn,
    windows,
    r05_movement,
    r08_fire,
    r10_resolution,
    r13_rout,
    r14_rally,
    r16_defensive_fire,
    r20_close_combat,
    r21_setup,
    r23_demolition,
    r24_smoke,
    r25_concealment,
    r27_sewer,
    r30_vehicle_movement,
    r31_transport,
    r34_afv_vs_infantry,
    r35_overrun,
    r36_infantry_vs_afv,
    r37_at_weapons,
    r38_fate,
)
