from __future__ import annotations

from html import escape

from .models import ActiveGame, DIFFICULTIES
from .scoring import format_duration
from .solver import board_to_line, find_rule_conflicts, find_wrong_cells

BOARD_TEMPLATE = r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <style>
    body {
      margin: 0;
      padding: 28px;
      background: #f6f4ef;
      color: #28231f;
      font-family: "Microsoft YaHei", "Noto Sans SC", Arial, sans-serif;
    }
    .card {
      width: 760px;
      margin: 0 auto;
      padding: 28px 30px 24px;
      border-radius: 28px;
      background: linear-gradient(145deg, #fffdf8, #efe8dc);
      box-shadow: 0 18px 45px rgba(45, 35, 25, .18);
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      gap: 16px;
      margin-bottom: 18px;
    }
    h1 {
      margin: 0;
      font-size: 34px;
      letter-spacing: .04em;
    }
    .meta {
      color: #73685c;
      font-size: 18px;
      line-height: 1.6;
      text-align: right;
    }
    table.board {
      border-collapse: collapse;
      margin: 0 auto;
      border: 6px solid #2d2925;
      background: #fffaf0;
    }
    td {
      width: 68px;
      height: 68px;
      text-align: center;
      vertical-align: middle;
      border: 1.5px solid #8f8378;
      font-size: 36px;
      line-height: 1;
      color: #2e2a26;
    }
    td.box-right { border-right-width: 5px; border-right-color: #2d2925; }
    td.box-bottom { border-bottom-width: 5px; border-bottom-color: #2d2925; }
    td.given {
      font-weight: 900;
      color: #171412;
      background: #efe3d1;
    }
    td.user {
      font-weight: 700;
      color: #165a99;
      background: #e9f4ff;
    }
    td.empty {
      color: transparent;
      background: #fffaf0;
    }
    td.conflict {
      color: #fff;
      background: #cf3f3f;
    }
    .candidates {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      grid-template-rows: repeat(3, 1fr);
      width: 100%;
      height: 100%;
      box-sizing: border-box;
      padding: 6px;
      color: #897c70;
      font-size: 13px;
      line-height: 1;
      font-weight: 600;
    }
    .candidates span {
      display: flex;
      align-items: center;
      justify-content: center;
      min-width: 0;
      min-height: 0;
    }
    .footer {
      display: flex;
      justify-content: space-between;
      margin-top: 18px;
      color: #6c6156;
      font-size: 16px;
    }
    .legend span {
      display: inline-block;
      margin-right: 14px;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h1>{{ title }}</h1>
      <div class="meta">
        <div>难度：{{ difficulty_label }} · 题目数：{{ givens }}</div>
        <div>用时：{{ elapsed }} · 错误：{{ mistakes }}</div>
      </div>
    </div>
    <table class="board">
      {% for row in rows %}
      <tr>
        {% for cell in row %}
        <td class="{{ cell.classes }}">
          {% if cell.value %}
            {{ cell.value }}
          {% elif show_candidates and cell.candidates %}
            <div class="candidates">
              {% for candidate in cell.candidates %}
                <span>{{ candidate }}</span>
              {% endfor %}
            </div>
          {% else %}
            ·
          {% endif %}
        </td>
        {% endfor %}
      </tr>
      {% endfor %}
    </table>
    <div class="footer">
      <div class="legend"><span>深色=题目</span><span>蓝色=填写</span><span>红色=冲突/错误</span></div>
      <div>{{ subtitle }}</div>
    </div>
  </div>
</body>
</html>
"""


def build_board_data(
    game: ActiveGame,
    *,
    title: str = "Sudoku Super",
    subtitle: str = "发送 /sudoku set 行 列 数字，或直接发送：行 列 数字",
    reveal_solution: bool = False,
    conflict_cells: set[int] | None = None,
    show_candidates: bool = False,
    candidates: list[list[str]] | None = None,
    now: float | None = None,
) -> dict:
    board = game.solution if reveal_solution else game.current
    conflicts = set(conflict_cells or set())
    if not reveal_solution:
        conflicts |= find_rule_conflicts(game.current)
        conflicts |= find_wrong_cells(game.current, game.solution)

    rows: list[list[dict[str, str]]] = []
    for r in range(9):
        row: list[dict[str, str]] = []
        for c in range(9):
            idx = r * 9 + c
            value = board[idx]
            classes = []
            if game.fixed[idx] and not reveal_solution:
                classes.append("given")
            elif value:
                classes.append("user")
            else:
                classes.append("empty")
            if idx in conflicts:
                classes.append("conflict")
            if c in {2, 5}:
                classes.append("box-right")
            if r in {2, 5}:
                classes.append("box-bottom")
            candidate_marks = [""] * 9
            if show_candidates and not value and candidates and idx < len(candidates):
                candidate_set = {str(v) for v in candidates[idx]}
                candidate_marks = [str(i) if str(i) in candidate_set else "" for i in range(1, 10)]
            row.append(
                {
                    "value": str(value) if value else "",
                    "classes": " ".join(classes),
                    "candidates": candidate_marks,
                }
            )
        rows.append(row)

    elapsed = 0.0 if now is None else max(0.0, now - game.started_at)
    profile = DIFFICULTIES[game.difficulty]
    return {
        "title": title,
        "subtitle": subtitle,
        "difficulty_label": profile.label,
        "givens": game.givens,
        "mistakes": game.mistakes,
        "elapsed": format_duration(elapsed),
        "rows": rows,
        "show_candidates": show_candidates,
    }


def plain_board(board: list[int]) -> str:
    """Return a readable text board for platforms without image rendering."""

    lines = []
    for r in range(9):
        values = []
        for c in range(9):
            value = board[r * 9 + c]
            values.append(str(value) if value else "·")
            if c in {2, 5}:
                values.append("│")
        lines.append(" ".join(values))
        if r in {2, 5}:
            lines.append("──────┼───────┼──────")
    return "\n".join(lines)


def safe_text(text: str) -> str:
    return escape(text, quote=False)


def compact_board(board: list[int]) -> str:
    return board_to_line(board, empty=".")
