from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import Board
from .solver import board_to_line, candidates_for_cell


@dataclass(frozen=True)
class AdvancedAnalysis:
    ok: bool
    status: str
    engine_version: str
    grid: str
    candidates: list[list[str]]
    steps: list[dict[str, Any]]
    solution_count: int | None = None
    solution_status: str | None = None
    error: str | None = None
    raw: dict[str, Any] | None = None


class AdvancedSolverError(RuntimeError):
    pass


class AdvancedSudokuAnalyzer:
    def __init__(
        self,
        *,
        plugin_dir: str | Path,
        sdk_dir: str | Path | None = None,
        node_executable: str = "node",
        timeout_seconds: float = 5.0,
    ):
        self.plugin_dir = Path(plugin_dir)
        self.sdk_dir = Path(sdk_dir) if sdk_dir else self.plugin_dir / "sdk" / "sudoku-wasm"
        self.node_executable = node_executable or "node"
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.runner_path = self.plugin_dir / "sudoku_super" / "wasm_runner.mjs"

    def availability_error(self) -> str | None:
        if not self.runner_path.exists():
            return f"找不到 WASM runner：{self.runner_path}"
        if not (self.sdk_dir / "sudoku_wasm.js").exists():
            return f"找不到 sudoku_wasm.js：{self.sdk_dir}"
        if not (self.sdk_dir / "sudoku_wasm_bg.wasm").exists():
            return f"找不到 sudoku_wasm_bg.wasm：{self.sdk_dir}"
        if shutil.which(self.node_executable) is None and not Path(self.node_executable).exists():
            return f"找不到 Node.js 可执行文件：{self.node_executable}"
        return None

    def analyze(self, board: Board, *, mode: str = "one_step") -> AdvancedAnalysis:
        normalized_mode = normalize_analysis_mode(mode)
        availability_error = self.availability_error()
        if availability_error:
            raise AdvancedSolverError(availability_error)

        request = {
            "puzzle": {
                "preset": "standard_9x9",
                "grid": board_to_line(board, empty="0"),
            },
            "mode": normalized_mode,
        }
        try:
            completed = subprocess.run(
                [self.node_executable, str(self.runner_path), str(self.sdk_dir)],
                input=json.dumps(request, ensure_ascii=False),
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdvancedSolverError(f"WASM 高级分析超时（>{self.timeout_seconds:.0f}s）") from exc
        except OSError as exc:
            raise AdvancedSolverError(f"无法启动 Node.js：{exc}") from exc

        output = (completed.stdout or "").strip()
        if not output:
            detail = (completed.stderr or "").strip()
            raise AdvancedSolverError(f"WASM 高级分析无输出：{detail}")
        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise AdvancedSolverError(f"WASM 高级分析返回了非 JSON 输出：{output[:300]}") from exc

        return AdvancedAnalysis(
            ok=bool(payload.get("ok")),
            status=str(payload.get("status") or "unknown"),
            engine_version=str(payload.get("engineVersion") or ""),
            grid=str(payload.get("grid") or ""),
            candidates=_normalize_candidates(payload.get("candidates")),
            steps=list(payload.get("steps") or []),
            solution_count=payload.get("solutionCount"),
            solution_status=payload.get("solutionStatus"),
            error=payload.get("error"),
            raw=payload,
        )


def normalize_analysis_mode(mode: str | None) -> str:
    value = (mode or "one_step").strip().casefold().replace("-", "_")
    if value in {"one", "step", "hint", "one_step", "下一步", "提示"}:
        return "one_step"
    if value in {"full", "path", "full_path", "solve", "完整", "完整路径"}:
        return "full_path"
    raise ValueError("高级解题模式只能是 one_step/下一步 或 full_path/完整路径")


def local_candidate_lists(board: Board) -> list[list[str]]:
    values: list[list[str]] = []
    for idx, value in enumerate(board):
        if value:
            values.append([])
        else:
            values.append([str(v) for v in sorted(candidates_for_cell(board, idx))])
    return values


def format_analysis(analysis: AdvancedAnalysis, *, max_steps: int = 5) -> str:
    if not analysis.ok:
        return f"高级解题引擎返回错误：{analysis.error or analysis.status}"

    lines = [
        "🧠 高级解题分析",
        f"状态：{_status_name(analysis.status)}"
        + (
            f"｜解状态：{_solution_status_name(analysis.solution_status)}"
            if analysis.solution_status
            else ""
        ),
    ]
    if analysis.solution_count is not None:
        lines[-1] += f"｜解数：{analysis.solution_count}"
    if analysis.engine_version:
        lines.append(f"引擎：{analysis.engine_version}")

    if not analysis.steps:
        lines.append("当前没有可直接应用的逻辑步骤。")
        return "\n".join(lines)

    lines.append("建议步骤：")
    for i, step in enumerate(analysis.steps[: max(1, max_steps)], 1):
        lines.append(f"{i}. {_format_step(step)}")
    if len(analysis.steps) > max_steps:
        lines.append(f"……共 {len(analysis.steps)} 步，仅显示前 {max_steps} 步。")
    return "\n".join(lines)


def _normalize_candidates(raw: Any) -> list[list[str]]:
    if not isinstance(raw, list):
        return [[] for _ in range(81)]
    result: list[list[str]] = []
    for item in raw[:81]:
        if isinstance(item, list):
            result.append([str(v) for v in item])
        else:
            result.append([])
    while len(result) < 81:
        result.append([])
    return result


def _format_step(step: dict[str, Any]) -> str:
    technique = _technique_name(str(step.get("technique") or "unknown"))
    conclusions = step.get("conclusions") or []
    pieces: list[str] = []
    for conclusion in conclusions[:6]:
        if not isinstance(conclusion, dict):
            continue
        cell = _cell_name(conclusion.get("cell"))
        symbol = conclusion.get("symbol")
        kind = conclusion.get("kind")
        if kind == "assign":
            pieces.append(f"{cell} = {symbol}")
        elif kind == "eliminate":
            pieces.append(f"{cell} 删除候选 {symbol}")
        else:
            pieces.append(f"{cell} {kind or ''} {symbol or ''}".strip())
    if len(conclusions) > 6:
        pieces.append(f"另 {len(conclusions) - 6} 项")
    return technique + ("：" + "；".join(pieces) if pieces else "")


def _cell_name(cell: Any) -> str:
    try:
        idx = int(cell)
    except Exception:
        return f"格 {cell}"
    return f"R{idx // 9 + 1}C{idx % 9 + 1}"


def _technique_name(value: str) -> str:
    names = {
        "nakedSingle": "唯余数",
        "hiddenSingle": "隐性唯一",
        "lockedCandidates": "锁定候选",
        "nakedSubset": "显性数组",
        "hiddenSubset": "隐性数组",
        "xWing": "X-Wing",
        "swordfish": "Swordfish",
    }
    return names.get(value, value)


def _status_name(value: str) -> str:
    names = {
        "solved": "已解出",
        "progress": "可继续推进",
        "stuck": "暂时卡住",
        "invalid": "无效盘面",
    }
    return names.get(value, value)


def _solution_status_name(value: str | None) -> str:
    names = {
        "unique": "唯一解",
        "multiple": "多解",
        "none": "无解",
        "unknown": "未知",
    }
    return names.get(value or "", value or "未知")
