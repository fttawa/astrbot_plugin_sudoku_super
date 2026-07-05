import unittest

from sudoku_super.solver import (
    assess_difficulty,
    count_solutions,
    find_rule_conflicts,
    is_complete,
    parse_board,
    solve_one,
)


class SolverTests(unittest.TestCase):
    def test_known_puzzle_has_unique_solution(self):
        puzzle = parse_board(
            "530070000"
            "600195000"
            "098000060"
            "800060003"
            "400803001"
            "700020006"
            "060000280"
            "000419005"
            "000080079"
        )
        solution = solve_one(puzzle)
        self.assertIsNotNone(solution)
        self.assertTrue(is_complete(solution))
        self.assertEqual(count_solutions(puzzle, limit=2), 1)

    def test_multi_solution_empty_board_is_limited(self):
        self.assertEqual(count_solutions([0] * 81, limit=2), 2)

    def test_conflict_detection(self):
        board = [0] * 81
        board[0] = 5
        board[1] = 5
        self.assertEqual(find_rule_conflicts(board), {0, 1})
        self.assertIsNone(solve_one(board))

    def test_assessment_returns_rating(self):
        puzzle = parse_board(
            "530070000"
            "600195000"
            "098000060"
            "800060003"
            "400803001"
            "700020006"
            "060000280"
            "000419005"
            "000080079"
        )
        assessment = assess_difficulty(puzzle)
        self.assertGreaterEqual(assessment.rating, 0)
        self.assertEqual(assessment.givens, 30)


if __name__ == "__main__":
    unittest.main()
