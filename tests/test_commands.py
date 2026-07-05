import unittest

from sudoku_super.commands import normalize_rank_scope, parse_command_value, parse_move_text


class CommandParsingTests(unittest.TestCase):
    def test_parse_shorthand_moves(self):
        self.assertEqual(parse_move_text("1 2 9").index, 1)
        self.assertEqual(parse_move_text("1 2 9").value, 9)
        self.assertEqual(parse_move_text("s 9,8,0").row, 8)
        self.assertEqual(parse_move_text("r3c4=5").col, 3)
        self.assertEqual(parse_move_text("1，2，清空").value, 0)
        self.assertIsNone(parse_move_text("/sudoku set 1 2 3"))
        self.assertIsNone(parse_move_text("今天 1 2 3"))

    def test_parse_command_value(self):
        self.assertEqual(parse_command_value("清空"), 0)
        self.assertEqual(parse_command_value("9"), 9)
        with self.assertRaises(ValueError):
            parse_command_value("10")

    def test_rank_scope_aliases(self):
        self.assertEqual(normalize_rank_scope("群内"), "group")
        self.assertEqual(normalize_rank_scope("global"), "global")
        with self.assertRaises(ValueError):
            normalize_rank_scope("weekly")


if __name__ == "__main__":
    unittest.main()
