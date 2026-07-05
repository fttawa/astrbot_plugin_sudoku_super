from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Board = list[int]


@dataclass(frozen=True)
class DifficultyProfile:
    """Generation, rating and scoring defaults for one difficulty."""

    key: str
    label: str
    aliases: tuple[str, ...]
    givens_min: int
    givens_max: int
    min_rating: int
    max_rating: int | None
    base_score: int
    target_seconds: int
    symmetric: bool = True

    def accepts_rating(self, rating: int) -> bool:
        if rating < self.min_rating:
            return False
        return self.max_rating is None or rating <= self.max_rating


DIFFICULTIES: dict[str, DifficultyProfile] = {
    "easy": DifficultyProfile(
        key="easy",
        label="简单",
        aliases=("easy", "simple", "入门", "简单", "简易"),
        givens_min=40,
        givens_max=46,
        min_rating=0,
        max_rating=4500,
        base_score=1000,
        target_seconds=8 * 60,
    ),
    "medium": DifficultyProfile(
        key="medium",
        label="中等",
        aliases=("medium", "normal", "中等", "普通", "标准"),
        givens_min=33,
        givens_max=39,
        min_rating=250,
        max_rating=8500,
        base_score=1800,
        target_seconds=15 * 60,
    ),
    "hard": DifficultyProfile(
        key="hard",
        label="困难",
        aliases=("hard", "困难", "难"),
        givens_min=29,
        givens_max=33,
        min_rating=650,
        max_rating=18000,
        base_score=3000,
        target_seconds=25 * 60,
    ),
    "hell": DifficultyProfile(
        key="hell",
        label="地狱",
        aliases=("hell", "地狱", "炼狱", "极难"),
        givens_min=25,
        givens_max=29,
        min_rating=1200,
        max_rating=None,
        base_score=5000,
        target_seconds=45 * 60,
    ),
    "demon": DifficultyProfile(
        key="demon",
        label="恶魔",
        aliases=("demon", "evil", "devil", "恶魔", "魔鬼"),
        givens_min=22,
        givens_max=26,
        min_rating=1800,
        max_rating=None,
        base_score=8000,
        target_seconds=75 * 60,
    ),
}

_DIFFICULTY_ALIASES = {
    alias.casefold(): key
    for key, profile in DIFFICULTIES.items()
    for alias in (profile.key, profile.label, *profile.aliases)
}


def normalize_difficulty(raw: str | None) -> str:
    """Normalize user supplied difficulty text to an internal key."""

    if not raw:
        return "medium"
    value = raw.strip().casefold()
    if value in _DIFFICULTY_ALIASES:
        return _DIFFICULTY_ALIASES[value]
    raise ValueError(f"未知难度：{raw}")


@dataclass
class DifficultyAssessment:
    rating: int
    givens: int
    unresolved_after_logic: int
    search_nodes: int
    max_depth: int
    singles: int
    hidden_singles: int


@dataclass
class Puzzle:
    difficulty: str
    puzzle: Board
    solution: Board
    assessment: DifficultyAssessment

    @property
    def givens(self) -> int:
        return sum(1 for value in self.puzzle if value)


@dataclass
class ActiveGame:
    game_id: str
    session_id: str
    user_id: str
    user_name: str
    difficulty: str
    puzzle: Board
    solution: Board
    current: Board
    fixed: list[bool]
    mistakes: int
    started_at: float
    updated_at: float
    history: list[Board] = field(default_factory=list)

    @property
    def givens(self) -> int:
        return sum(1 for value in self.puzzle if value)

    @property
    def empty_count(self) -> int:
        return sum(1 for value in self.current if value == 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "difficulty": self.difficulty,
            "puzzle": self.puzzle,
            "solution": self.solution,
            "current": self.current,
            "fixed": self.fixed,
            "mistakes": self.mistakes,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActiveGame":
        return cls(
            game_id=str(data["game_id"]),
            session_id=str(data["session_id"]),
            user_id=str(data["user_id"]),
            user_name=str(data.get("user_name") or data["user_id"]),
            difficulty=str(data["difficulty"]),
            puzzle=[int(v) for v in data["puzzle"]],
            solution=[int(v) for v in data["solution"]],
            current=[int(v) for v in data["current"]],
            fixed=[bool(v) for v in data["fixed"]],
            mistakes=int(data.get("mistakes", 0)),
            started_at=float(data["started_at"]),
            updated_at=float(data["updated_at"]),
            history=[[int(v) for v in board] for board in data.get("history", [])],
        )


@dataclass(frozen=True)
class Move:
    row: int
    col: int
    value: int

    @property
    def index(self) -> int:
        return self.row * 9 + self.col
