import unittest

from sudoku_super.generator import SudokuGenerator
from sudoku_super.models import DIFFICULTIES
from sudoku_super.solver import count_solutions, is_valid_board, solve_one


class GeneratorTests(unittest.TestCase):
    def test_all_difficulties_generate_unique_valid_puzzles(self):
        for offset, (key, profile) in enumerate(DIFFICULTIES.items()):
            with self.subTest(key=key):
                puzzle = SudokuGenerator(timeout_seconds=8, seed=20260705 + offset).generate(key)
                self.assertTrue(is_valid_board(puzzle.puzzle))
                self.assertTrue(is_valid_board(puzzle.solution))
                self.assertEqual(count_solutions(puzzle.puzzle, limit=2), 1)
                self.assertEqual(solve_one(puzzle.puzzle), puzzle.solution)
                self.assertGreaterEqual(puzzle.givens, profile.givens_min)
                self.assertLessEqual(puzzle.givens, profile.givens_max)
                self.assertTrue(profile.accepts_rating(puzzle.assessment.rating))


if __name__ == "__main__":
    unittest.main()
