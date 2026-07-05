import tempfile
import time
import unittest

from sudoku_super.models import ActiveGame
from sudoku_super.storage import SudokuStorage


def make_game(user_id="u1", session_id="s1", score_board=None):
    puzzle = score_board or [0] * 81
    solution = [((i * 3 + i // 9) % 9) + 1 for i in range(81)]
    now = time.time()
    return ActiveGame(
        game_id=f"game-{user_id}",
        session_id=session_id,
        user_id=user_id,
        user_name=f"name-{user_id}",
        difficulty="easy",
        puzzle=puzzle,
        solution=solution,
        current=puzzle.copy(),
        fixed=[bool(v) for v in puzzle],
        mistakes=0,
        started_at=now - 60,
        updated_at=now,
        history=[],
    )


class StorageTests(unittest.TestCase):
    def test_active_game_round_trip_and_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = SudokuStorage(tmp)
            game = make_game()
            storage.save_active_game(game)
            loaded = storage.get_active_game("s1", "u1")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.game_id, game.game_id)
            storage.record_completion(loaded, score=1234, elapsed_seconds=42)
            self.assertIsNone(storage.get_active_game("s1", "u1"))
            rows = storage.leaderboard("group", "s1", 10)
            self.assertEqual(rows[0]["score"], 1234)
            stats = storage.user_stats("group", "s1", "u1")
            self.assertEqual(stats["completed_count"], 1)
            storage.close()

    def test_global_and_group_leaderboards_are_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = SudokuStorage(tmp)
            game1 = make_game("u1", "s1")
            game2 = make_game("u2", "s2")
            storage.record_completion(game1, score=100, elapsed_seconds=50)
            storage.record_completion(game2, score=200, elapsed_seconds=70)
            self.assertEqual(len(storage.leaderboard("group", "s1", 10)), 1)
            self.assertEqual(storage.leaderboard("global", "s1", 10)[0]["user_id"], "u2")
            storage.close()


if __name__ == "__main__":
    unittest.main()
