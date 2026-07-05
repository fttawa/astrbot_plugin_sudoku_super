from __future__ import annotations

import random
import time
from dataclasses import dataclass

from .models import DIFFICULTIES, Puzzle, normalize_difficulty
from .solver import assess_difficulty, count_givens, count_solutions, generate_full_solution


class GenerationTimeout(TimeoutError):
    """Raised when no puzzle matching the requested profile is generated in time."""


@dataclass
class SudokuGenerator:
    timeout_seconds: float = 12.0
    seed: int | None = None
    max_attempts: int = 500

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def generate(self, difficulty: str) -> Puzzle:
        key = normalize_difficulty(difficulty)
        profile = DIFFICULTIES[key]
        deadline = time.monotonic() + max(1.0, float(self.timeout_seconds))
        attempts = 0

        while time.monotonic() < deadline and attempts < self.max_attempts:
            attempts += 1
            solution = generate_full_solution(self._rng)
            target_givens = self._rng.randint(profile.givens_min, profile.givens_max)
            puzzle = self._dig_holes(solution, target_givens, profile.key, deadline)
            if puzzle is None:
                continue
            givens = count_givens(puzzle)
            if not (profile.givens_min <= givens <= profile.givens_max):
                continue
            assessment = assess_difficulty(puzzle)
            if profile.accepts_rating(assessment.rating):
                return Puzzle(profile.key, puzzle, solution, assessment)

        raise GenerationTimeout(f"{profile.label}题目生成超时，请稍后重试")

    def _dig_holes(
        self,
        solution: list[int],
        target_givens: int,
        difficulty_key: str,
        deadline: float,
    ) -> list[int] | None:
        board = solution.copy()
        pairs = self._removal_pairs(difficulty_key)

        for pair in pairs:
            if time.monotonic() >= deadline:
                return None
            removable = [idx for idx in pair if board[idx] != 0]
            if not removable:
                continue
            if count_givens(board) - len(removable) < target_givens:
                continue
            backup = [(idx, board[idx]) for idx in removable]
            for idx in removable:
                board[idx] = 0
            if count_solutions(board, limit=2) != 1:
                for idx, value in backup:
                    board[idx] = value
            if count_givens(board) <= target_givens:
                break

        # If symmetry made the exact target unreachable, try a small number of
        # single-cell removals while preserving uniqueness. This keeps generated
        # puzzles inside the configured range without sacrificing validity.
        singles = [idx for idx, value in enumerate(board) if value]
        self._rng.shuffle(singles)
        for idx in singles:
            if time.monotonic() >= deadline or count_givens(board) <= target_givens:
                break
            old = board[idx]
            board[idx] = 0
            if count_solutions(board, limit=2) != 1:
                board[idx] = old

        return board

    def _removal_pairs(self, difficulty_key: str) -> list[tuple[int, ...]]:
        seen: set[int] = set()
        pairs: list[tuple[int, ...]] = []
        for idx in range(81):
            if idx in seen:
                continue
            opposite = 80 - idx
            pair = tuple(sorted({idx, opposite}))
            seen.update(pair)
            pairs.append(pair)

        if difficulty_key in {"hell", "demon"}:
            # Scattered order: shuffle inside box bands first, then globally.
            pairs.sort(key=lambda pair: (self._rng.random(), min(pair) // 9 % 3, min(pair) % 3))
        else:
            self._rng.shuffle(pairs)
        return pairs
