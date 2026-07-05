import shutil
import unittest
from pathlib import Path

from sudoku_super.advanced_solver import AdvancedSudokuAnalyzer, format_analysis, local_candidate_lists
from sudoku_super.solver import parse_board


class AdvancedSolverTests(unittest.TestCase):
    def test_local_candidate_lists(self):
        board = parse_board(
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
        candidates = local_candidate_lists(board)
        self.assertIn("1", candidates[2])
        self.assertEqual(candidates[0], [])

    def test_missing_sdk_reports_unavailable(self):
        plugin_dir = Path(__file__).resolve().parents[1]
        analyzer = AdvancedSudokuAnalyzer(plugin_dir=plugin_dir, sdk_dir=plugin_dir / "missing-sdk", timeout_seconds=5)
        self.assertIn("找不到 sudoku_wasm.js", analyzer.availability_error())

    @unittest.skipIf(shutil.which("node") is None, "Node.js is required for minimal bundled WASM runtime test")
    def test_minimal_bundled_wasm_one_step(self):
        plugin_dir = Path(__file__).resolve().parents[1]
        analyzer = AdvancedSudokuAnalyzer(
            plugin_dir=plugin_dir,
            timeout_seconds=5,
        )
        self.assertIsNone(analyzer.availability_error())
        board = parse_board(
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
        analysis = analyzer.analyze(board, mode="one_step")
        self.assertTrue(analysis.ok)
        self.assertEqual(len(analysis.candidates), 81)
        self.assertGreaterEqual(len(analysis.steps), 1)
        self.assertIn("高级解题分析", format_analysis(analysis))


if __name__ == "__main__":
    unittest.main()
