from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .models import ActiveGame


class SudokuStorage:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "sudoku_super.sqlite3"
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _init_db(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS active_games (
                    game_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    puzzle TEXT NOT NULL,
                    solution TEXT NOT NULL,
                    current TEXT NOT NULL,
                    fixed TEXT NOT NULL,
                    mistakes INTEGER NOT NULL DEFAULT 0,
                    started_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    history TEXT NOT NULL DEFAULT '[]',
                    UNIQUE(session_id, user_id)
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS completed_games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    elapsed_seconds REAL NOT NULL,
                    mistakes INTEGER NOT NULL,
                    givens INTEGER NOT NULL,
                    started_at REAL NOT NULL,
                    completed_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_completed_scope ON completed_games(session_id, user_id, score)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_completed_global ON completed_games(user_id, score)"
            )

    def get_active_game(self, session_id: str, user_id: str) -> ActiveGame | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM active_games WHERE session_id = ? AND user_id = ?",
                (session_id, user_id),
            ).fetchone()
        return self._row_to_game(row) if row else None

    def save_active_game(self, game: ActiveGame) -> None:
        payload = self._game_to_payload(game)
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO active_games (
                    game_id, session_id, user_id, user_name, difficulty,
                    puzzle, solution, current, fixed, mistakes, started_at, updated_at, history
                )
                VALUES (
                    :game_id, :session_id, :user_id, :user_name, :difficulty,
                    :puzzle, :solution, :current, :fixed, :mistakes, :started_at, :updated_at, :history
                )
                ON CONFLICT(session_id, user_id) DO UPDATE SET
                    game_id = excluded.game_id,
                    user_name = excluded.user_name,
                    difficulty = excluded.difficulty,
                    puzzle = excluded.puzzle,
                    solution = excluded.solution,
                    current = excluded.current,
                    fixed = excluded.fixed,
                    mistakes = excluded.mistakes,
                    started_at = excluded.started_at,
                    updated_at = excluded.updated_at,
                    history = excluded.history
                """,
                payload,
            )

    def delete_active_game(self, session_id: str, user_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM active_games WHERE session_id = ? AND user_id = ?",
                (session_id, user_id),
            )

    def record_completion(self, game: ActiveGame, score: int, elapsed_seconds: float) -> None:
        completed_at = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO completed_games (
                    session_id, user_id, user_name, difficulty, score,
                    elapsed_seconds, mistakes, givens, started_at, completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game.session_id,
                    game.user_id,
                    game.user_name,
                    game.difficulty,
                    int(score),
                    float(elapsed_seconds),
                    int(game.mistakes),
                    int(game.givens),
                    float(game.started_at),
                    completed_at,
                ),
            )
            self._conn.execute(
                "DELETE FROM active_games WHERE session_id = ? AND user_id = ?",
                (game.session_id, game.user_id),
            )

    def leaderboard(self, scope: str, session_id: str, limit: int) -> list[dict[str, Any]]:
        where = "WHERE session_id = ?" if scope == "group" else ""
        params: tuple[Any, ...] = (session_id,) if scope == "group" else ()
        sql = f"""
            WITH scoped AS (
                SELECT * FROM completed_games {where}
            ),
            best AS (
                SELECT
                    *,
                    ROW_NUMBER() OVER (
                        PARTITION BY user_id
                        ORDER BY score DESC, elapsed_seconds ASC, mistakes ASC, completed_at ASC
                    ) AS rn,
                    COUNT(*) OVER (PARTITION BY user_id) AS completed_count
                FROM scoped
            )
            SELECT * FROM best
            WHERE rn = 1
            ORDER BY score DESC, elapsed_seconds ASC, mistakes ASC
            LIMIT ?
        """
        with self._lock:
            rows = self._conn.execute(sql, (*params, int(limit))).fetchall()
        return [dict(row) for row in rows]

    def user_stats(self, scope: str, session_id: str, user_id: str) -> dict[str, Any] | None:
        where = "session_id = ? AND user_id = ?" if scope == "group" else "user_id = ?"
        params: tuple[Any, ...] = (session_id, user_id) if scope == "group" else (user_id,)
        sql = f"""
            SELECT
                user_id,
                COALESCE(MAX(user_name), user_id) AS user_name,
                COUNT(*) AS completed_count,
                MAX(score) AS best_score,
                AVG(elapsed_seconds) AS avg_elapsed,
                MIN(elapsed_seconds) AS best_elapsed,
                SUM(mistakes) AS total_mistakes
            FROM completed_games
            WHERE {where}
            GROUP BY user_id
        """
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _json(data: Any) -> str:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _loads(data: str) -> Any:
        return json.loads(data)

    def _game_to_payload(self, game: ActiveGame) -> dict[str, Any]:
        return {
            "game_id": game.game_id,
            "session_id": game.session_id,
            "user_id": game.user_id,
            "user_name": game.user_name,
            "difficulty": game.difficulty,
            "puzzle": self._json(game.puzzle),
            "solution": self._json(game.solution),
            "current": self._json(game.current),
            "fixed": self._json(game.fixed),
            "mistakes": game.mistakes,
            "started_at": game.started_at,
            "updated_at": game.updated_at,
            "history": self._json(game.history),
        }

    def _row_to_game(self, row: sqlite3.Row) -> ActiveGame:
        return ActiveGame(
            game_id=row["game_id"],
            session_id=row["session_id"],
            user_id=row["user_id"],
            user_name=row["user_name"],
            difficulty=row["difficulty"],
            puzzle=[int(v) for v in self._loads(row["puzzle"])],
            solution=[int(v) for v in self._loads(row["solution"])],
            current=[int(v) for v in self._loads(row["current"])],
            fixed=[bool(v) for v in self._loads(row["fixed"])],
            mistakes=int(row["mistakes"]),
            started_at=float(row["started_at"]),
            updated_at=float(row["updated_at"]),
            history=[[int(v) for v in board] for board in self._loads(row["history"])],
        )
