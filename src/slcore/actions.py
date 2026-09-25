"""The table of command handlers of the core (M3, PR-34).

Each action of `commands.ACTIONS` has one handler record here, and the rule module of the
action registers it with `@action(...)`. The record holds the function that applies the
command and the properties the engine reads around it:

- `unconceals`: the act of rule 25.4 and rule 42.2 that the action is (a move, a shot,
  smoke, a charge), or empty for no act. The act takes the concealment counter of the
  acting units and puts a hidden unit on the board.
- `acting`: the units that act, when they are not the units of the command. The fire of a
  group is the act of each member of the group.
- `conceal_on_arrival`: rule 27.5, a stack that comes up from a sewer is covered.

Each command window of `slcore.phases.PHASE_STEPS` has one generator of its legal
commands, registered with `@window(name)` by the sub-step name. So a new action needs one
registration, and it cannot leave a firer concealed by being absent from a hand-written
list. `tests/core/test_action_table.py` holds the table to `commands.ACTIONS` and to the
window sub-steps.

This module imports no other module of the core at run time, so each rule module can
import it. `ACTION_SPECS`, `UNCONCEALING`, and `WINDOWS` import `slcore.handlers` on the
first read, so the tables are complete for a reader that does not build an engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from slcore.commands import Command
    from slcore.events import Event
    from slcore.game import State

CAUSE_MOVED = "the unit moved"
CAUSE_FIRED = "the unit fired"
CAUSE_SMOKE = "the unit made smoke"
CAUSE_CHARGE = "the unit placed a charge"

# (engine, state, command) gives the next state and its events. The engine is the static
# context of the game: its board, counter types, tables, and rule contexts.
ApplyFn = Callable[[Any, "State", "Command"], "tuple[State, list[Event]]"]
# (state before the command, command) gives the units that act.
ActingFn = Callable[["State", "Command"], "tuple[int, ...]"]
# (engine, state, sub-step) gives the legal commands of the window, in frame sequence.
WindowFn = Callable[[Any, "State", Any], "list[Command]"]


@dataclass(frozen=True)
class ActionSpec:
    """One action: how the core applies it, and what it is for rules 25.4, 27.5, and 42.2."""

    name: str
    apply: ApplyFn
    unconceals: str = ""
    acting: ActingFn | None = None
    conceal_on_arrival: bool = False
    module: str = ""

    def acting_units(self, before: "State", command: "Command") -> tuple[int, ...]:
        """The units whose act takes their concealment counter off (rule 25.4)."""
        if self.acting is None:
            return command.units
        return self.acting(before, command)


_SPECS: dict[str, ActionSpec] = {}
_UNCONCEALING: dict[str, str] = {}
_WINDOWS: dict[str, WindowFn] = {}


def action(
    name: str,
    *,
    unconceals: str = "",
    acting: ActingFn | None = None,
    conceal_on_arrival: bool = False,
) -> Callable[[ApplyFn], ApplyFn]:
    """Register the function below as the handler of the action `name`."""

    def register(fn: ApplyFn) -> ApplyFn:
        if name in _SPECS:
            raise ValueError(f"the action {name!r} has a handler in {_SPECS[name].module} already")
        _SPECS[name] = ActionSpec(name, fn, unconceals, acting, conceal_on_arrival, fn.__module__)
        if unconceals:
            _UNCONCEALING[name] = unconceals
        return fn

    return register


def window(name: str) -> Callable[[WindowFn], WindowFn]:
    """Register the function below as the generator of the window sub-step `name`."""

    def register(fn: WindowFn) -> WindowFn:
        if name in _WINDOWS:
            raise ValueError(f"the window {name!r} has a generator already")
        _WINDOWS[name] = fn
        return fn

    return register


def specs() -> dict[str, ActionSpec]:
    """The live table of the handlers. The engine imports each handler module first."""
    return _SPECS


def windows() -> dict[str, WindowFn]:
    """The live table of the window generators."""
    return _WINDOWS


def __getattr__(name: str) -> Any:
    tables = {"ACTION_SPECS": _SPECS, "UNCONCEALING": _UNCONCEALING, "WINDOWS": _WINDOWS}
    if name in tables:
        from slcore import handlers  # noqa: F401  (each handler module registers on import)

        return tables[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
