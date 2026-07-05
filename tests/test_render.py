import time
import unittest

from sudoku_super.models import ActiveGame
from sudoku_super.render import build_board_data, plain_board


class RenderTests(unittest.TestCase):
    def test_board_data_marks_given_user_and_conflict_cells(self):
        now = time.time()
        puzzle = [0] * 81
        puzzle[0] = 1
        current = puzzle.copy()
        current[1] = 2
        solution = [1, 3] + [0] * 79
        game = ActiveGame(
            game_id="g",
            session_id="s",
            user_id="u",
            user_name="n",
            difficulty="easy",
            puzzle=puzzle,
            solution=solution,
            current=current,
            fixed=[bool(v) for v in puzzle],
            mistakes=1,
            started_at=now - 5,
            updated_at=now,
            history=[],
        )
        data = build_board_data(
            game,
            title="T",
            conflict_cells={1},
            show_candidates=True,
            candidates=[[] for _ in range(81)],
            now=now,
        )
        self.assertIn("given", data["rows"][0][0]["classes"])
        self.assertIn("user", data["rows"][0][1]["classes"])
        self.assertIn("conflict", data["rows"][0][1]["classes"])
        self.assertIn("5秒", data["elapsed"])
        self.assertTrue(data["show_candidates"])

    def test_board_data_includes_candidate_marks(self):
        now = time.time()
        game = ActiveGame(
            game_id="g",
            session_id="s",
            user_id="u",
            user_name="n",
            difficulty="easy",
            puzzle=[0] * 81,
            solution=[0] * 81,
            current=[0] * 81,
            fixed=[False] * 81,
            mistakes=0,
            started_at=now,
            updated_at=now,
            history=[],
        )
        candidates = [[] for _ in range(81)]
        candidates[0] = ["1", "5", "9"]
        data = build_board_data(game, show_candidates=True, candidates=candidates, now=now)
        self.assertEqual(data["rows"][0][0]["value"], "")
        self.assertEqual(data["rows"][0][0]["candidates"], ["1", "", "", "", "5", "", "", "", "9"])

    def test_plain_board_contains_separators(self):
        text = plain_board([0] * 81)
        self.assertIn("│", text)
        self.assertIn("·", text)


if __name__ == "__main__":
    unittest.main()
