from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable

from .models import Board, DifficultyAssessment

ALL_MASK = (1 << 9) - 1
ROWS = tuple(tuple(r * 9 + c for c in range(9)) for r in range(9))
COLS = tuple(tuple(r * 9 + c for r in range(9)) for c in range(9))
BOXES = tuple(
    tuple((br + dr) * 9 + bc + dc for dr in range(3) for dc in range(3))
    for br in (0, 3, 6)
    for bc in (0, 3, 6)
)
UNITS = ROWS + COLS + BOXES
BOX_INDEX = tuple((r // 3) * 3 + (c // 3) for r in range(9) for c in range(9))


class SudokuError(ValueError):
    """Raised when a board cannot represent a valid Sudoku state."""


@dataclass
class _State:
    board: Board
    row_masks: list[int]
    col_masks: list[int]
    box_masks: list[int]
    empties: list[int]


@dataclass
class _SearchMetrics:
    nodes: int = 0
    max_depth: int = 0
    branch_sum: int = 0
    truncated: bool = False


def parse_board(raw: str | Iterable[int]) -> Board:
    """Parse a board from 81 chars/integers. 0, dot and underscore mean empty."""

    if isinstance(raw, str):
        chars = [ch for ch in raw if ch.isdigit() or ch in "._"]
        if len(chars) != 81:
            raise SudokuError("数独棋盘必须包含 81 个格子")
        board = [0 if ch in "0._" else int(ch) for ch in chars]
    else:
        board = [int(v) for v in raw]
        if len(board) != 81:
            raise SudokuError("数独棋盘必须包含 81 个格子")
    if any(v < 0 or v > 9 for v in board):
        raise SudokuError("数独格子只能是 0-9")
    return board


def board_to_line(board: Board, empty: str = "0") -> str:
    return "".join(str(value) if value else empty for value in board)


def count_givens(board: Board) -> int:
    return sum(1 for value in board if value)


def is_complete(board: Board) -> bool:
    return all(value != 0 for value in board) and is_valid_board(board)


def is_valid_board(board: Board) -> bool:
    return _init_state(board) is not None


def find_rule_conflicts(board: Board) -> set[int]:
    """Return cells that violate row, column or box uniqueness."""

    conflicts: set[int] = set()
    for unit in UNITS:
        seen: dict[int, int] = {}
        for idx in unit:
            value = board[idx]
            if not value:
                continue
            other = seen.get(value)
            if other is None:
                seen[value] = idx
            else:
                conflicts.add(other)
                conflicts.add(idx)
    return conflicts


def find_wrong_cells(current: Board, solution: Board) -> set[int]:
    return {idx for idx, value in enumerate(current) if value and value != solution[idx]}


def solve_one(board: Board, *, randomize: bool = False, rng: random.Random | None = None) -> Board | None:
    state = _init_state(board)
    if state is None:
        return None
    solution: Board | None = None
    rng = rng or random.Random()

    def search(pos: int) -> bool:
        nonlocal solution
        if pos == len(state.empties):
            solution = state.board.copy()
            return True

        best = _choose_best_empty(state, pos)
        if best < 0:
            return False
        state.empties[pos], state.empties[best] = state.empties[best], state.empties[pos]
        idx = state.empties[pos]
        mask = _candidate_mask_for_state(state, idx)
        if mask == 0:
            state.empties[pos], state.empties[best] = state.empties[best], state.empties[pos]
            return False

        bits = _mask_bits(mask)
        if randomize:
            rng.shuffle(bits)
        for bit in bits:
            _place_bit(state, idx, bit)
            if search(pos + 1):
                return True
            _remove_bit(state, idx, bit)
        state.empties[pos], state.empties[best] = state.empties[best], state.empties[pos]
        return False

    search(0)
    return solution


def count_solutions(board: Board, *, limit: int = 2) -> int:
    state = _init_state(board)
    if state is None:
        return 0
    count = 0

    def search(pos: int) -> None:
        nonlocal count
        if count >= limit:
            return
        if pos == len(state.empties):
            count += 1
            return

        best = _choose_best_empty(state, pos)
        if best < 0:
            return
        state.empties[pos], state.empties[best] = state.empties[best], state.empties[pos]
        idx = state.empties[pos]
        mask = _candidate_mask_for_state(state, idx)
        if mask:
            for bit in _mask_bits(mask):
                _place_bit(state, idx, bit)
                search(pos + 1)
                _remove_bit(state, idx, bit)
                if count >= limit:
                    break
        state.empties[pos], state.empties[best] = state.empties[best], state.empties[pos]

    search(0)
    return count


def has_unique_solution(board: Board) -> bool:
    return count_solutions(board, limit=2) == 1


def generate_full_solution(rng: random.Random | None = None) -> Board:
    """Generate a randomized completed Sudoku grid."""

    rng = rng or random.Random()
    board = [0] * 81
    # Seeding diagonal boxes reduces backtracking while preserving randomness.
    for box_id in (0, 4, 8):
        digits = list(range(1, 10))
        rng.shuffle(digits)
        for idx, value in zip(BOXES[box_id], digits):
            board[idx] = value
    solution = solve_one(board, randomize=True, rng=rng)
    if solution is None:
        # Extremely unlikely after valid diagonal seeding; retry from scratch.
        return generate_full_solution(rng)
    return solution


def assess_difficulty(board: Board, *, node_limit: int = 50_000) -> DifficultyAssessment:
    """Rate a puzzle using simple logical reduction plus MRV search metrics."""

    working = board.copy()
    singles, hidden_singles, valid = _logic_reduce(working)
    unresolved = sum(1 for value in working if value == 0)
    metrics = _SearchMetrics()
    if valid and unresolved:
        _measure_search(working, metrics, node_limit=node_limit)
    elif not valid:
        metrics.nodes = node_limit
        metrics.truncated = True

    rating = (
        unresolved * 55
        + max(0, metrics.nodes - 1) * 9
        + metrics.max_depth * 28
        + metrics.branch_sum * 2
        + max(0, count_givens(board) - 17) // 2
    )
    if metrics.truncated:
        rating += node_limit // 2
    return DifficultyAssessment(
        rating=int(rating),
        givens=count_givens(board),
        unresolved_after_logic=unresolved,
        search_nodes=metrics.nodes,
        max_depth=metrics.max_depth,
        singles=singles,
        hidden_singles=hidden_singles,
    )


def candidates_for_cell(board: Board, index: int) -> set[int]:
    state = _init_state(board)
    if state is None or board[index]:
        return set()
    return {_bit_to_digit(bit) for bit in _mask_bits(_candidate_mask_for_state(state, index))}


def _init_state(board: Board) -> _State | None:
    if len(board) != 81:
        return None
    row_masks = [0] * 9
    col_masks = [0] * 9
    box_masks = [0] * 9
    empties: list[int] = []
    copied = [int(v) for v in board]
    for idx, value in enumerate(copied):
        if value == 0:
            empties.append(idx)
            continue
        if value < 1 or value > 9:
            return None
        bit = 1 << (value - 1)
        row, col, box = idx // 9, idx % 9, BOX_INDEX[idx]
        if row_masks[row] & bit or col_masks[col] & bit or box_masks[box] & bit:
            return None
        row_masks[row] |= bit
        col_masks[col] |= bit
        box_masks[box] |= bit
    return _State(copied, row_masks, col_masks, box_masks, empties)


def _candidate_mask_for_state(state: _State, idx: int) -> int:
    row, col, box = idx // 9, idx % 9, BOX_INDEX[idx]
    return ALL_MASK & ~(state.row_masks[row] | state.col_masks[col] | state.box_masks[box])


def _choose_best_empty(state: _State, start: int) -> int:
    best = -1
    best_count = 10
    for pos in range(start, len(state.empties)):
        idx = state.empties[pos]
        if state.board[idx] != 0:
            continue
        count = _candidate_mask_for_state(state, idx).bit_count()
        if count < best_count:
            best = pos
            best_count = count
            if count <= 1:
                break
    return best


def _place_bit(state: _State, idx: int, bit: int) -> None:
    state.board[idx] = _bit_to_digit(bit)
    row, col, box = idx // 9, idx % 9, BOX_INDEX[idx]
    state.row_masks[row] |= bit
    state.col_masks[col] |= bit
    state.box_masks[box] |= bit


def _remove_bit(state: _State, idx: int, bit: int) -> None:
    state.board[idx] = 0
    row, col, box = idx // 9, idx % 9, BOX_INDEX[idx]
    state.row_masks[row] &= ~bit
    state.col_masks[col] &= ~bit
    state.box_masks[box] &= ~bit


def _mask_bits(mask: int) -> list[int]:
    bits: list[int] = []
    while mask:
        bit = mask & -mask
        bits.append(bit)
        mask ^= bit
    return bits


def _bit_to_digit(bit: int) -> int:
    return bit.bit_length()


def _logic_reduce(board: Board) -> tuple[int, int, bool]:
    singles = 0
    hidden_singles = 0
    while True:
        state = _init_state(board)
        if state is None:
            return singles, hidden_singles, False

        progress = False
        for idx in state.empties:
            mask = _candidate_mask_for_state(state, idx)
            if mask == 0:
                return singles, hidden_singles, False
            if mask.bit_count() == 1:
                board[idx] = _bit_to_digit(mask)
                singles += 1
                progress = True
                break
        if progress:
            continue

        for unit in UNITS:
            present = {board[idx] for idx in unit if board[idx]}
            missing = [digit for digit in range(1, 10) if digit not in present]
            for digit in missing:
                bit = 1 << (digit - 1)
                cells: list[int] = []
                state = _init_state(board)
                if state is None:
                    return singles, hidden_singles, False
                for idx in unit:
                    if board[idx] == 0 and (_candidate_mask_for_state(state, idx) & bit):
                        cells.append(idx)
                        if len(cells) > 1:
                            break
                if len(cells) == 0:
                    return singles, hidden_singles, False
                if len(cells) == 1:
                    board[cells[0]] = digit
                    hidden_singles += 1
                    progress = True
                    break
            if progress:
                break
        if not progress:
            return singles, hidden_singles, True


def _measure_search(board: Board, metrics: _SearchMetrics, *, node_limit: int) -> bool:
    state = _init_state(board)
    if state is None:
        metrics.truncated = True
        return False

    def search(pos: int, depth: int) -> bool:
        if metrics.nodes >= node_limit:
            metrics.truncated = True
            return False
        if pos == len(state.empties):
            return True
        best = _choose_best_empty(state, pos)
        if best < 0:
            return False
        state.empties[pos], state.empties[best] = state.empties[best], state.empties[pos]
        idx = state.empties[pos]
        mask = _candidate_mask_for_state(state, idx)
        if mask == 0:
            state.empties[pos], state.empties[best] = state.empties[best], state.empties[pos]
            return False
        bits = _mask_bits(mask)
        metrics.nodes += 1
        metrics.max_depth = max(metrics.max_depth, depth)
        metrics.branch_sum += len(bits)
        for bit in bits:
            _place_bit(state, idx, bit)
            if search(pos + 1, depth + 1):
                return True
            _remove_bit(state, idx, bit)
            if metrics.truncated:
                break
        state.empties[pos], state.empties[best] = state.empties[best], state.empties[pos]
        return False

    return search(0, 1)
