"""The check of an uploaded game: the save file lines, played again through the core.

The collector keeps a game only when each command is legal in its frame and gives the hash
that the player's game recorded. A game from a package with other rules or another board
gives another hash, so the check finds it, and the collector keeps it apart as not verified.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from slcore.commands import Command
from slhost.savegame import SaveFileError, check_lines
from slhost.server import SOURCE_HUMAN, SOURCE_ROUTE

# The sources of a decision of a person: a command, and the steps of a move to a far hex.
HUMAN_SOURCES = frozenset({SOURCE_HUMAN, SOURCE_ROUTE})
# The engines of the last scenarios, because the build of a board takes seconds.
ENGINE_LIMIT = 4


@dataclass(frozen=True)
class GameCheck:
    game_id: str
    scenario: str
    commands: int
    human_commands: int
    verified: bool
    game_over: bool
    result: str
    reason: str


class GameRejected(ValueError):
    """An upload that the collector does not keep: not a save file, or no decision of a person."""


def human_count(lines: list[dict[str, Any]]) -> int:
    return sum(1 for line in lines if line.get("source") in HUMAN_SOURCES)


class Verifier:
    """Plays uploaded games again. One engine for each recent scenario, shared by the threads."""

    def __init__(self, scenarios: frozenset[str]) -> None:
        self.scenarios = scenarios
        self._engines: OrderedDict[tuple[str, str | None], Any] = OrderedDict()
        self._lock = threading.Lock()

    def _engine(self, scenario: str, board: str | None) -> Any:
        from slagents.registry import build_engine

        key = (scenario, board)
        with self._lock:
            if key in self._engines:
                self._engines.move_to_end(key)
                return self._engines[key]
        engine = build_engine(scenario, board)
        with self._lock:
            self._engines[key] = engine
            while len(self._engines) > ENGINE_LIMIT:
                self._engines.popitem(last=False)
        return engine

    def check(self, game: list[dict[str, Any]]) -> GameCheck:
        """The result of the replay. A game that is not a save file, or that has no decision
        of a person, is a `GameRejected`; a replay that does not agree is `verified` False."""
        try:
            header, lines = check_lines(game, "the uploaded game")
        except SaveFileError as exc:
            raise GameRejected(str(exc)) from exc
        game_id = str(header["game_id"])
        scenario = str(header["scenario"])
        if scenario not in self.scenarios:
            raise GameRejected(f"the scenario {scenario!r} is not a scenario of this collector")
        humans = human_count(lines)
        if humans == 0:
            raise GameRejected("the game has no decision of a person")
        board = header.get("board")
        engine = self._engine(scenario, board if isinstance(board, str) else None)
        switches = header.get("switches") or None
        try:
            state = engine.new_game(int(header["seed"]), switches)
        except (TypeError, ValueError) as exc:
            raise GameRejected(f"the header does not start a game: {exc}") from exc
        for index, line in enumerate(lines):
            if state.game_over:
                return GameCheck(game_id, scenario, len(lines), humans, False, True, state.result, f"command {index} is after the end of the game")
            frame = engine.legal_commands(state)
            try:
                command_id = str(line.get("command_id") or Command.from_payload(line["payload"]).id)
            except (KeyError, TypeError, ValueError) as exc:
                return GameCheck(game_id, scenario, len(lines), humans, False, False, "", f"command {index} has no valid payload: {exc}")
            legal = frame.by_id(command_id)
            if legal is None:
                return GameCheck(game_id, scenario, len(lines), humans, False, False, "", f"command {index} is not legal in the replay")
            state, _ = engine.apply(state, legal.command, frame)
            if engine.hash_state(state) != line["hash"]:
                return GameCheck(game_id, scenario, len(lines), humans, False, False, "", f"command {index} gives another hash")
        return GameCheck(game_id, scenario, len(lines), humans, True, bool(state.game_over), str(state.result or ""), "")
