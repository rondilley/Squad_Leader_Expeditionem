"""The SQLite index of the runs (FR-57).

The index answers cross-run questions without a read of every artifact. It is a
cache: `rebuild` throws it away and reads the artifacts again. An upsert of the same
run twice changes nothing, so a rebuild is safe at any time.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from slruns import artifact

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    slug TEXT NOT NULL,
    started TEXT NOT NULL,
    path TEXT NOT NULL,
    scenario TEXT,
    board TEXT,
    games INTEGER,
    config TEXT NOT NULL,
    stats TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_kind ON runs (kind);
CREATE INDEX IF NOT EXISTS runs_started ON runs (started);
CREATE TABLE IF NOT EXISTS results (
    run_id TEXT NOT NULL,
    game INTEGER NOT NULL,
    seed INTEGER NOT NULL,
    agent_a TEXT NOT NULL,
    agent_b TEXT NOT NULL,
    side_a TEXT NOT NULL,
    result TEXT NOT NULL,
    turns INTEGER NOT NULL,
    commands INTEGER NOT NULL,
    PRIMARY KEY (run_id, game),
    FOREIGN KEY (run_id) REFERENCES runs (id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS elo (
    run_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    rating REAL NOT NULL,
    games INTEGER NOT NULL,
    PRIMARY KEY (run_id, agent),
    FOREIGN KEY (run_id) REFERENCES runs (id) ON DELETE CASCADE
);
"""

DEFAULT_PATH = "runs/runs.sqlite"


class IndexError_(Exception):
    """The index could not be opened or written."""


def connect(path: str | Path = DEFAULT_PATH) -> sqlite3.Connection:
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(p)
    except (OSError, sqlite3.Error) as exc:
        raise IndexError_(f"cannot open the run index at {p}: {exc}") from exc
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA)
    except sqlite3.Error as exc:
        conn.close()
        raise IndexError_(f"cannot prepare the run index at {p}: {exc}") from exc
    return conn


def upsert(conn: sqlite3.Connection, directory: str | Path, commit: bool = True) -> str:
    """Put one run artifact in the index. The same run twice changes nothing."""
    d = Path(directory)
    doc = artifact.read(d)
    manifest = doc["manifest"]
    stats = doc["stats"]
    config = manifest.get("config", {})
    run_id = str(manifest["id"])
    try:
        conn.execute(
            """
            INSERT INTO runs (id, kind, slug, started, path, scenario, board, games, config, stats)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                kind=excluded.kind, slug=excluded.slug, started=excluded.started, path=excluded.path,
                scenario=excluded.scenario, board=excluded.board, games=excluded.games,
                config=excluded.config, stats=excluded.stats
            """,
            (
                run_id,
                str(manifest["kind"]),
                str(manifest["slug"]),
                str(manifest["started"]),
                str(d.as_posix()),
                config.get("scenario"),
                config.get("board"),
                stats.get("games"),
                json.dumps(config, sort_keys=True),
                json.dumps(stats, sort_keys=True),
            ),
        )
        conn.execute("DELETE FROM results WHERE run_id = ?", (run_id,))
        for i, row in enumerate(stats.get("results", [])):
            conn.execute(
                "INSERT INTO results (run_id, game, seed, agent_a, agent_b, side_a, result, turns, commands) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    i,
                    int(row["seed"]),
                    str(row["agent_a"]),
                    str(row["agent_b"]),
                    str(row["side_a"]),
                    str(row["result"]),
                    int(row.get("turns", 0)),
                    int(row.get("commands", 0)),
                ),
            )
        conn.execute("DELETE FROM elo WHERE run_id = ?", (run_id,))
        for agent, entry in stats.get("elo", {}).items():
            conn.execute(
                "INSERT INTO elo (run_id, agent, rating, games) VALUES (?, ?, ?, ?)",
                (run_id, str(agent), float(entry["rating"]), int(entry["games"])),
            )
        if commit:
            conn.commit()
    except (sqlite3.Error, KeyError, TypeError, ValueError) as exc:
        if commit:
            conn.rollback()
        raise IndexError_(f"cannot index the run at {d}: {exc}") from exc
    return run_id


def rebuild(conn: sqlite3.Connection, root: str | Path = "runs") -> int:
    """Replace the index from the run directory, in one transaction.

    A delete that commits before the new rows are in leaves an empty index when a
    later artifact fails. The delete and the inserts commit together, or not at all.
    """
    try:
        conn.execute("DELETE FROM runs")
        count = 0
        for directory in artifact.find_runs(root):
            upsert(conn, directory, commit=False)
            count += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return count


def list_runs(conn: sqlite3.Connection, kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    if kind:
        rows = conn.execute("SELECT * FROM runs WHERE kind = ? ORDER BY started DESC LIMIT ?", (kind, limit))
    else:
        rows = conn.execute("SELECT * FROM runs ORDER BY started DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


def elo_history(conn: sqlite3.Connection, agent: str) -> list[dict[str, Any]]:
    """The Elo of one agent across the runs, oldest first (OR-04)."""
    rows = conn.execute(
        "SELECT runs.started, runs.id, elo.rating, elo.games FROM elo JOIN runs ON runs.id = elo.run_id WHERE elo.agent = ? ORDER BY runs.started",
        (agent,),
    )
    return [dict(r) for r in rows]


def win_counts(conn: sqlite3.Connection, run_id: str) -> dict[str, int]:
    rows = conn.execute("SELECT result, COUNT(*) AS n FROM results WHERE run_id = ? GROUP BY result", (run_id,))
    return {str(r["result"]): int(r["n"]) for r in rows}
