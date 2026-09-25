"""The position corpus: the pictures and the statistics of many games, with the result.

A game gives one position at the end of each Movement Phase and each Advance Phase of
each player turn, because those are the moments a player has put the counters where
the player wants them. A position has the picture, the statistics of each side, the
turn, the phase that ended, the phasing player, and the side that won the game.

The corpus is one `.npz` file and one JSON index. The games run in a pool of workers,
each with its own engine, and each worker gives back the positions of its game.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from slagents.base import decide
from slagents.registry import build_engine, make_agent
from slcore.game import PHASE_ADVANCE, PHASE_MOVEMENT
from slshape import features, picture

RECORDED_PHASES = (PHASE_MOVEMENT, PHASE_ADVANCE)
MAX_COMMANDS = 20000

# One engine and its fixed planes for each scenario in each worker.
_ENGINES: dict[str, tuple[Any, np.ndarray, dict[str, Any], dict[int, Any]]] = {}


class CorpusError(Exception):
    """A corpus that cannot be written or read."""


@dataclass
class Corpus:
    """The positions of a set of games, as arrays with one row for each position."""

    scenario: str
    board: str
    plane_names: tuple[str, ...]
    feature_names: tuple[str, ...]
    pictures: np.ndarray  # [N, planes, cols, rows + 1] uint8
    feats: np.ndarray  # [N, 2, features] float32: the statistics of player 0 and of player 1
    game: np.ndarray  # [N] the index of the game in `games`
    turn: np.ndarray  # [N]
    phasing: np.ndarray  # [N] the player whose phase ended
    phase: np.ndarray  # [N] 0 for the Movement Phase, 1 for the Advance Phase
    winner: np.ndarray  # [N] the player that won the game, or -1 for a draw
    games: list[dict[str, Any]] = field(default_factory=list)

    @property
    def size(self) -> int:
        return int(self.pictures.shape[0])

    def write(self, directory: str | Path) -> Path:
        out = Path(directory)
        try:
            out.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(
                out / "corpus.npz",
                pictures=self.pictures,
                feats=self.feats,
                game=self.game,
                turn=self.turn,
                phasing=self.phasing,
                phase=self.phase,
                winner=self.winner,
            )
            (out / "corpus.json").write_text(
                json.dumps(
                    {
                        "scenario": self.scenario,
                        "board": self.board,
                        "plane_names": list(self.plane_names),
                        "feature_names": list(self.feature_names),
                        "positions": self.size,
                        "games": self.games,
                    },
                    indent=1,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            raise CorpusError(f"cannot write the corpus in {out}: {exc}") from exc
        return out

    @staticmethod
    def read(directory: str | Path) -> "Corpus":
        out = Path(directory)
        try:
            index = json.loads((out / "corpus.json").read_text(encoding="utf-8"))
            with np.load(out / "corpus.npz") as arrays:
                return Corpus(
                    scenario=str(index["scenario"]),
                    board=str(index["board"]),
                    plane_names=tuple(index["plane_names"]),
                    feature_names=tuple(index["feature_names"]),
                    pictures=arrays["pictures"],
                    feats=arrays["feats"],
                    game=arrays["game"],
                    turn=arrays["turn"],
                    phasing=arrays["phasing"],
                    phase=arrays["phase"],
                    winner=arrays["winner"],
                    games=list(index["games"]),
                )
        except (OSError, KeyError, ValueError) as exc:
            raise CorpusError(f"cannot read the corpus in {out}: {exc}") from exc


def _engine_for(scenario: str) -> tuple[Any, np.ndarray, dict[str, Any], dict[int, Any]]:
    found = _ENGINES.get(scenario)
    if found is None:
        engine = build_engine(scenario, None)
        objectives = picture.objective_buildings(engine)
        fixed = picture.terrain_planes(engine.board, objectives)
        buildings_of = features.side_buildings(engine, objectives)
        found = (engine, fixed, objectives, buildings_of)
        _ENGINES[scenario] = found
    return found


def positions_of_game(scenario: str, seed: int, first: str, second: str) -> dict[str, Any]:
    """One game in a worker: its positions and its result."""
    engine, fixed, objectives, buildings_of = _engine_for(scenario)
    agents = (make_agent(first, engine, seed, 0), make_agent(second, engine, seed, 1))
    state = engine.new_game(seed)
    pictures: list[np.ndarray] = []
    feats: list[np.ndarray] = []
    labels: list[tuple[int, int, int]] = []
    steps = 0
    error = None
    try:
        while not state.game_over and steps < MAX_COMMANDS:
            frame = engine.legal_commands(state)
            chosen = frame.by_id(decide(agents[frame.player], state, frame))
            before = state
            state, _ = engine.apply(state, chosen.command, frame)
            steps += 1
            if before.phase in RECORDED_PHASES and state.phase != before.phase:
                pictures.append(picture.picture(engine.board, before, engine.types, fixed, objectives))
                feats.append(
                    np.stack(
                        [
                            features.features_of(engine, before, objectives, buildings_of, 0),
                            features.features_of(engine, before, objectives, buildings_of, 1),
                        ]
                    )
                )
                labels.append((before.turn, before.phasing, RECORDED_PHASES.index(before.phase)))
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:200]}"
    sides = tuple(engine.scenario.players())
    winner = -1
    if state.game_over and state.result in sides:
        winner = sides.index(state.result)
    return {
        "seed": seed,
        "agents": [first, second],
        "result": state.result if state.game_over else None,
        "turns": state.turn,
        "winner": winner,
        "error": error,
        "board": engine.board.name,
        "pictures": np.stack(pictures) if pictures else np.zeros((0,) + picture.shape_of(engine.board), dtype=np.uint8),
        "feats": np.stack(feats) if feats else np.zeros((0, 2, len(features.FEATURE_NAMES)), dtype=np.float32),
        "labels": labels,
    }


def _job(job: tuple[str, int, str, str]) -> dict[str, Any]:
    return positions_of_game(*job)


def record_corpus(
    scenario: str,
    pairs: Sequence[tuple[str, str]],
    games: int,
    first_seed: int,
    workers: int = 1,
    progress: bool = False,
) -> Corpus:
    """Play `games` of each pair, half with the sides swapped, and collect the positions.

    A game that ends in a draw or an error stays in the index and gives no position,
    because a position with no winner teaches nothing about winning.
    """
    jobs: list[tuple[str, int, str, str]] = []
    seed = first_seed
    for first, second in pairs:
        for g in range(games):
            order = (first, second) if g % 2 == 0 else (second, first)
            jobs.append((scenario, seed, order[0], order[1]))
            seed += 1
    started = time.perf_counter()
    if workers <= 1 or len(jobs) < 2:
        results = [_job(job) for job in jobs]
    else:
        from slagents.registry import limit_workers

        workers = limit_workers(workers)
        with Pool(processes=min(workers, len(jobs))) as pool:
            results = list(pool.imap(_job, jobs, chunksize=1))
    pictures: list[np.ndarray] = []
    feats: list[np.ndarray] = []
    game_index: list[int] = []
    turn: list[int] = []
    phasing: list[int] = []
    phase: list[int] = []
    winner: list[int] = []
    index: list[dict[str, Any]] = []
    board = ""
    for gi, result in enumerate(results):
        board = result["board"]
        index.append({k: result[k] for k in ("seed", "agents", "result", "turns", "winner", "error")})
        if progress:
            print(f"game {gi + 1} of {len(results)}: {result['agents']} seed {result['seed']} -> {result['result'] or result['error']} ({(time.perf_counter() - started) / 60:.1f} min)", flush=True)
        if result["winner"] < 0 or result["error"]:
            continue
        pictures.append(result["pictures"])
        feats.append(result["feats"])
        for t, p, ph in result["labels"]:
            game_index.append(gi)
            turn.append(t)
            phasing.append(p)
            phase.append(ph)
            winner.append(result["winner"])
    engine, _fixed, _objectives, _buildings = _engine_for(scenario)
    empty_pictures = np.zeros((0,) + picture.shape_of(engine.board), dtype=np.uint8)
    empty_feats = np.zeros((0, 2, len(features.FEATURE_NAMES)), dtype=np.float32)
    return Corpus(
        scenario=scenario,
        board=board,
        plane_names=picture.PLANE_NAMES,
        feature_names=features.FEATURE_NAMES,
        pictures=np.concatenate(pictures) if pictures else empty_pictures,
        feats=np.concatenate(feats) if feats else empty_feats,
        game=np.array(game_index, dtype=np.int32),
        turn=np.array(turn, dtype=np.int32),
        phasing=np.array(phasing, dtype=np.int32),
        phase=np.array(phase, dtype=np.int32),
        winner=np.array(winner, dtype=np.int32),
        games=index,
    )
