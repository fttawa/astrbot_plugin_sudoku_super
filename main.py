from __future__ import annotations

import asyncio
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

# AstrBot v4.26.x imports plugin main.py from the core package context, and
# the plugin directory is not always present on sys.path. Add it explicitly so
# sibling packages such as sudoku_super can be imported reliably after install.
_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

# AstrBot can hot-reload main.py while leaving sibling modules in sys.modules.
# Drop this plugin's internal package cache so updated helpers (for example
# render.build_board_data signatures) are re-imported after plugin upgrades.
for _module_name in list(sys.modules):
    if _module_name == "sudoku_super" or _module_name.startswith("sudoku_super."):
        del sys.modules[_module_name]

from sudoku_super.advanced_solver import (
    AdvancedSolverError,
    AdvancedSudokuAnalyzer,
    format_analysis,
    local_candidate_lists,
    normalize_analysis_mode,
)
from sudoku_super.commands import normalize_rank_scope, parse_command_value, parse_move_text
from sudoku_super.generator import GenerationTimeout, SudokuGenerator
from sudoku_super.models import ActiveGame, DIFFICULTIES, Move, normalize_difficulty
from sudoku_super.render import BOARD_TEMPLATE, build_board_data, plain_board
from sudoku_super.scoring import calculate_score, format_duration
from sudoku_super.solver import find_rule_conflicts, find_wrong_cells
from sudoku_super.storage import SudokuStorage

PLUGIN_NAME = "astrbot_plugin_sudoku_super"


@register(PLUGIN_NAME, "fttawa", "带题目生成、棋盘图片、解题挑战和排行榜的数独插件", "1.1.2")
class SudokuSuperPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.storage = SudokuStorage(self._resolve_data_dir())
        self.advanced_analyzer = self._create_advanced_analyzer()

    async def initialize(self):
        logger.info("Sudoku Super 插件已加载")

    @filter.command_group("sudoku")
    def sudoku():
        """数独挑战：生成题目、填数、查看排行榜。"""

    @sudoku.command("help")
    async def sudoku_help(self, event: AstrMessageEvent):
        """查看数独插件帮助。"""
        yield event.plain_result(self._help_text())

    @sudoku.command("new")
    async def new_game(self, event: AstrMessageEvent, difficulty: str = "中等"):
        """开始一局新数独。用法：/sudoku new 中等"""
        session_id = self._session_id(event)
        user_id = self._user_id(event)
        user_name = self._user_name(event)
        active = self.storage.get_active_game(session_id, user_id)
        if active:
            yield event.plain_result(
                "你已经有一局进行中的数独，请先完成或发送 /sudoku giveup 放弃后再开新局。"
            )
            return

        try:
            key = normalize_difficulty(difficulty)
        except ValueError as exc:
            yield event.plain_result(f"{exc}\n可选难度：简单 / 中等 / 困难 / 地狱 / 恶魔")
            return

        profile = DIFFICULTIES[key]
        yield event.plain_result(f"正在生成【{profile.label}】数独题目，请稍候……")
        generator = SudokuGenerator(timeout_seconds=self._config_float("generate_timeout_seconds", 12.0))
        try:
            puzzle = await asyncio.to_thread(generator.generate, key)
        except GenerationTimeout as exc:
            yield event.plain_result(str(exc))
            return

        now = time.time()
        game = ActiveGame(
            game_id=uuid.uuid4().hex,
            session_id=session_id,
            user_id=user_id,
            user_name=user_name,
            difficulty=puzzle.difficulty,
            puzzle=puzzle.puzzle,
            solution=puzzle.solution,
            current=puzzle.puzzle.copy(),
            fixed=[value != 0 for value in puzzle.puzzle],
            mistakes=0,
            started_at=now,
            updated_at=now,
            history=[],
        )
        self.storage.save_active_game(game)
        text = (
            f"✅ 已开始【{profile.label}】数独挑战！\n"
            f"给定数：{game.givens}，难度评分：{puzzle.assessment.rating}\n"
            "填数：/sudoku set 行 列 数字，例如 /sudoku set 1 2 9\n"
            "也可以直接发送：1 2 9"
        )
        yield event.plain_result(text)
        async for result in self._board_results(event, game, title="新的数独挑战"):
            yield result

    @sudoku.command("set")
    async def set_cell(self, event: AstrMessageEvent, row: int, col: int, value: str):
        """填入或清空一个格子。用法：/sudoku set 1 2 9"""
        try:
            digit = parse_command_value(value)
        except ValueError as exc:
            yield event.plain_result(str(exc))
            return
        move = Move(row=int(row) - 1, col=int(col) - 1, value=digit)
        async for result in self._handle_move(event, move):
            yield result

    @sudoku.command("board")
    async def board(self, event: AstrMessageEvent):
        """查看当前棋盘。"""
        game = self._active_game_for_event(event)
        if not game:
            yield event.plain_result("你当前没有进行中的数独。发送 /sudoku new 中等 开始一局。")
            return
        async for result in self._board_results(event, game, title="当前数独棋盘"):
            yield result

    @sudoku.command("check")
    async def check(self, event: AstrMessageEvent):
        """检查当前进度。"""
        game = self._active_game_for_event(event)
        if not game:
            yield event.plain_result("你当前没有进行中的数独。")
            return
        conflicts = find_rule_conflicts(game.current) | find_wrong_cells(game.current, game.solution)
        if game.current == game.solution:
            async for result in self._complete_game(event, game):
                yield result
            return
        if conflicts:
            yield event.plain_result(f"发现 {len(conflicts)} 个冲突/错误格，已在棋盘中标红。")
        else:
            yield event.plain_result(f"当前没有冲突。剩余空格：{game.empty_count}，错误次数：{game.mistakes}")
        async for result in self._board_results(event, game, title="数独检查", conflict_cells=conflicts):
            yield result

    @sudoku.command("hint")
    async def hint(self, event: AstrMessageEvent, mode: str = "one_step"):
        """使用高级解题引擎给出下一步提示。"""
        async for result in self._hint_results(event, mode, title="高级解题提示"):
            yield result

    @sudoku.command("advanced")
    async def advanced(self, event: AstrMessageEvent, mode: str = "one_step"):
        """高级解题模式：one_step 下一步分析，full_path 完整路径。"""
        async for result in self._hint_results(event, mode, title="高级解题模式"):
            yield result

    @sudoku.command("analyze")
    async def analyze(self, event: AstrMessageEvent, mode: str = "full_path"):
        """高级分析当前盘面。用法：/sudoku analyze full_path"""
        game = self._active_game_for_event(event)
        if not game:
            yield event.plain_result("你当前没有进行中的数独。")
            return
        try:
            normalized_mode = normalize_analysis_mode(mode)
        except ValueError as exc:
            yield event.plain_result(str(exc))
            return
        if not self._config_bool("advanced_solver_enabled", True):
            yield event.plain_result("高级解题引擎已在配置中关闭。")
            async for result in self._board_results(event, game, title="当前数独棋盘"):
                yield result
            return
        try:
            analysis = await asyncio.to_thread(self.advanced_analyzer.analyze, game.current, mode=normalized_mode)
            yield event.plain_result(
                format_analysis(analysis, max_steps=self._config_int("advanced_solver_max_steps", 5))
            )
        except AdvancedSolverError as exc:
            yield event.plain_result(f"高级解题引擎不可用：{exc}")
        async for result in self._board_results(event, game, title="高级盘面分析"):
            yield result

    @sudoku.command("undo")
    async def undo(self, event: AstrMessageEvent):
        """撤销上一步正确填数或清空。"""
        game = self._active_game_for_event(event)
        if not game:
            yield event.plain_result("你当前没有进行中的数独。")
            return
        if not game.history:
            yield event.plain_result("没有可撤销的步骤。")
            return
        game.current = game.history.pop()
        game.updated_at = time.time()
        self.storage.save_active_game(game)
        yield event.plain_result("已撤销上一步。")
        async for result in self._board_results(event, game, title="撤销后棋盘"):
            yield result

    @sudoku.command("giveup")
    async def giveup(self, event: AstrMessageEvent):
        """放弃当前挑战，不计入排行榜。"""
        game = self._active_game_for_event(event)
        if not game:
            yield event.plain_result("你当前没有进行中的数独。")
            return
        self.storage.delete_active_game(game.session_id, game.user_id)
        yield event.plain_result("已放弃本局，本局不会计入排行榜。答案如下：")
        async for result in self._board_results(event, game, title="数独答案", reveal_solution=True):
            yield result

    @sudoku.command("answer")
    async def answer(self, event: AstrMessageEvent):
        """查看答案。查看后本局结束且不计入排行榜。"""
        if not self._config_bool("allow_answer", True):
            yield event.plain_result("当前配置禁止查看答案。")
            return
        game = self._active_game_for_event(event)
        if not game:
            yield event.plain_result("你当前没有进行中的数独。")
            return
        self.storage.delete_active_game(game.session_id, game.user_id)
        yield event.plain_result("答案如下。本局已结束，不计入排行榜。")
        async for result in self._board_results(event, game, title="数独答案", reveal_solution=True):
            yield result

    @sudoku.command("rank")
    async def rank(self, event: AstrMessageEvent, scope: str = "group"):
        """查看排行榜。用法：/sudoku rank group 或 /sudoku rank global"""
        try:
            normalized_scope = normalize_rank_scope(scope)
        except ValueError as exc:
            yield event.plain_result(str(exc))
            return
        limit = self._config_int("leaderboard_limit", 10)
        rows = self.storage.leaderboard(normalized_scope, self._session_id(event), limit)
        title = "群内排行榜" if normalized_scope == "group" else "全局排行榜"
        if not rows:
            yield event.plain_result(f"{title}暂无记录。完成一局数独后即可上榜。")
            return
        lines = [f"🏆 Sudoku Super {title}"]
        for index, row in enumerate(rows, 1):
            difficulty = DIFFICULTIES.get(row["difficulty"])
            diff_label = difficulty.label if difficulty else row["difficulty"]
            lines.append(
                f"{index}. {row['user_name']}｜{row['score']}分｜{diff_label}｜"
                f"{format_duration(row['elapsed_seconds'])}｜错{row['mistakes']}｜完成{row['completed_count']}局"
            )
        yield event.plain_result("\n".join(lines))

    @sudoku.command("stats")
    async def stats(self, event: AstrMessageEvent, target: str = ""):
        """查看自己或指定用户的群内统计。"""
        scope = "group"
        raw = (target or "").strip()
        if raw:
            try:
                scope = normalize_rank_scope(raw)
                user_id = self._user_id(event)
            except ValueError:
                user_id = self._extract_user_id_from_text(raw) or self._mentioned_user_id(event) or self._user_id(event)
        else:
            user_id = self._mentioned_user_id(event) or self._user_id(event)
        data = self.storage.user_stats(scope, self._session_id(event), user_id)
        if not data:
            yield event.plain_result("暂无完成记录。")
            return
        title = "群内" if scope == "group" else "全局"
        yield event.plain_result(
            f"📊 {data['user_name']} 的 Sudoku Super {title}统计\n"
            f"完成局数：{data['completed_count']}\n"
            f"最高分：{data['best_score']}\n"
            f"最快完成：{format_duration(data['best_elapsed'])}\n"
            f"平均用时：{format_duration(data['avg_elapsed'])}\n"
            f"累计错误：{data['total_mistakes'] or 0}"
        )

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def shorthand_move(self, event: AstrMessageEvent):
        """活跃对局中支持 1 2 9 / s 1 2 9 / 1,2,9 简写。"""
        move = parse_move_text(getattr(event, "message_str", ""))
        if move is None:
            return
        # 无活跃对局时忽略，避免普通聊天中的数字被打断。
        if not self._active_game_for_event(event):
            return
        async for result in self._handle_move(event, move):
            yield result
        # Stop propagation only after all responses have been yielded. Calling
        # this before yielding can make AstrBot stop after the first text
        # response and skip the following board image.
        event.stop_event()

    async def terminate(self):
        self.storage.close()
        logger.info("Sudoku Super 插件已卸载")

    async def _handle_move(self, event: AstrMessageEvent, move: Move):
        if not (0 <= move.row <= 8 and 0 <= move.col <= 8):
            yield event.plain_result("行列范围必须是 1-9。")
            game = self._active_game_for_event(event)
            if game:
                async for result in self._board_results(event, game, title="当前数独棋盘"):
                    yield result
            return
        game = self._active_game_for_event(event)
        if not game:
            yield event.plain_result("你当前没有进行中的数独。发送 /sudoku new 中等 开始一局。")
            return
        idx = move.index
        label = f"第 {move.row + 1} 行第 {move.col + 1} 列"
        if game.fixed[idx]:
            yield event.plain_result(f"{label} 是题目给定格，不能修改。")
            async for result in self._board_results(event, game, title="当前数独棋盘"):
                yield result
            return
        game.user_name = self._user_name(event)
        now = time.time()
        if move.value == 0:
            if game.current[idx] == 0:
                yield event.plain_result(f"{label} 已经是空格。")
                async for result in self._board_results(event, game, title="当前数独棋盘"):
                    yield result
                return
            self._push_history(game)
            game.current[idx] = 0
            game.updated_at = now
            self.storage.save_active_game(game)
            yield event.plain_result(f"已清空{label}。")
            async for result in self._board_results(event, game, title="清空后棋盘"):
                yield result
            return

        if move.value != game.solution[idx]:
            game.mistakes += 1
            game.updated_at = now
            self.storage.save_active_game(game)
            yield event.plain_result(
                f"❌ {label} 填 {move.value} 不正确，已计入错误次数。当前错误：{game.mistakes}"
            )
            async for result in self._board_results(event, game, title="当前数独棋盘"):
                yield result
            return

        if game.current[idx] == move.value:
            yield event.plain_result(f"{label} 已经是 {move.value}。")
            async for result in self._board_results(event, game, title="当前数独棋盘"):
                yield result
            return

        self._push_history(game)
        game.current[idx] = move.value
        game.updated_at = now
        if game.current == game.solution:
            async for result in self._complete_game(event, game):
                yield result
            return
        self.storage.save_active_game(game)
        yield event.plain_result(f"✅ 已填入：{label} = {move.value}。剩余空格：{game.empty_count}")
        async for result in self._board_results(event, game, title="填数后棋盘"):
            yield result

    async def _hint_results(self, event: AstrMessageEvent, mode: str, *, title: str):
        game = self._active_game_for_event(event)
        if not game:
            yield event.plain_result("你当前没有进行中的数独。")
            return
        try:
            normalized_mode = normalize_analysis_mode(mode)
        except ValueError as exc:
            yield event.plain_result(str(exc))
            return
        try:
            if not self._config_bool("advanced_solver_enabled", True):
                raise AdvancedSolverError("配置 advanced_solver_enabled 已关闭")
            analysis = await asyncio.to_thread(self.advanced_analyzer.analyze, game.current, mode=normalized_mode)
            yield event.plain_result(
                format_analysis(analysis, max_steps=self._config_int("advanced_solver_max_steps", 5))
            )
        except AdvancedSolverError as exc:
            yield event.plain_result(
                "高级解题引擎不可用，已使用基础候选数提示。\n"
                f"原因：{exc}\n"
                + self._basic_hint_text(game)
            )
        async for result in self._board_results(event, game, title=title):
            yield result

    async def _complete_game(self, event: AstrMessageEvent, game: ActiveGame):
        elapsed = max(0.0, time.time() - game.started_at)
        score = calculate_score(
            game.difficulty,
            elapsed,
            game.mistakes,
            time_bonus_ratio=self._config_float("time_bonus_ratio", 0.5),
            mistake_penalty_rate=self._config_float("mistake_penalty_rate", 0.08),
        )
        game.user_name = self._user_name(event)
        self.storage.record_completion(game, score, elapsed)
        profile = DIFFICULTIES[game.difficulty]
        yield event.plain_result(
            f"🎉 恭喜完成【{profile.label}】数独！\n"
            f"用时：{format_duration(elapsed)}｜错误：{game.mistakes}｜得分：{score}\n"
            "本局已计入群内与全局排行榜。"
        )
        async for result in self._board_results(event, game, title="挑战完成", reveal_solution=True):
            yield result

    async def _board_results(
        self,
        event: AstrMessageEvent,
        game: ActiveGame,
        *,
        title: str,
        reveal_solution: bool = False,
        conflict_cells: set[int] | None = None,
    ):
        url = await self._render_board_url(game, title=title, reveal_solution=reveal_solution, conflict_cells=conflict_cells)
        if url:
            yield event.image_result(url)
        else:
            board = game.solution if reveal_solution else game.current
            yield event.plain_result("图片渲染不可用，使用文本棋盘：\n" + plain_board(board))

    async def _render_board_url(
        self,
        game: ActiveGame,
        *,
        title: str,
        reveal_solution: bool = False,
        conflict_cells: set[int] | None = None,
    ) -> str | None:
        try:
            data = build_board_data(
                game,
                title=title,
                reveal_solution=reveal_solution,
                conflict_cells=conflict_cells,
                show_candidates=self._config_bool("show_candidates", False) and not reveal_solution,
                candidates=await self._candidate_lists(game) if self._config_bool("show_candidates", False) and not reveal_solution else None,
                now=time.time(),
            )
            return await self.html_render(
                BOARD_TEMPLATE,
                data,
                options={
                    "type": "png",
                    "full_page": True,
                    "timeout": 60_000,
                },
            )
        except Exception as exc:  # pragma: no cover - depends on AstrBot runtime renderer.
            logger.warning(f"数独棋盘 HTML 渲染失败，将降级为文本棋盘：{exc}")
            return None

    async def _candidate_lists(self, game: ActiveGame) -> list[list[str]]:
        source = str(self.config.get("candidate_source", "auto")).strip().casefold()
        if source in {"wasm", "advanced", "auto"} and self._config_bool("advanced_solver_enabled", True):
            try:
                analysis = await asyncio.to_thread(self.advanced_analyzer.analyze, game.current, mode="one_step")
                if analysis.ok and analysis.candidates:
                    return analysis.candidates
            except Exception as exc:
                if source in {"wasm", "advanced"}:
                    logger.warning(f"高级候选数获取失败，降级到本地候选数：{exc}")
                else:
                    logger.debug(f"高级候选数获取失败，降级到本地候选数：{exc}")
        return local_candidate_lists(game.current)

    def _active_game_for_event(self, event: AstrMessageEvent) -> ActiveGame | None:
        return self.storage.get_active_game(self._session_id(event), self._user_id(event))

    def _push_history(self, game: ActiveGame) -> None:
        game.history.append(game.current.copy())
        max_history = self._config_int("max_history", 30)
        if len(game.history) > max_history:
            del game.history[: len(game.history) - max_history]

    def _resolve_data_dir(self) -> Path:
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path

            return Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
        except Exception:
            return Path(__file__).resolve().parent / "data" / PLUGIN_NAME

    def _create_advanced_analyzer(self) -> AdvancedSudokuAnalyzer:
        raw_sdk_dir = str(self.config.get("advanced_solver_sdk_dir", "") or "").strip()
        sdk_dir = Path(raw_sdk_dir) if raw_sdk_dir else _PLUGIN_DIR / "sdk" / "sudoku-wasm"
        return AdvancedSudokuAnalyzer(
            plugin_dir=_PLUGIN_DIR,
            sdk_dir=sdk_dir,
            node_executable=str(self.config.get("node_executable", "node") or "node"),
            timeout_seconds=self._config_float("advanced_solver_timeout_seconds", 5.0),
        )

    @staticmethod
    def _basic_hint_text(game: ActiveGame) -> str:
        candidates = local_candidate_lists(game.current)
        best: tuple[int, list[str]] | None = None
        for idx, values in enumerate(candidates):
            if game.current[idx] == 0 and values and (best is None or len(values) < len(best[1])):
                best = (idx, values)
        if best is None:
            return "基础提示：当前没有可用候选数提示。"
        idx, values = best
        return f"基础提示：R{idx // 9 + 1}C{idx % 9 + 1} 的候选数为 {'/'.join(values)}。"

    @staticmethod
    def _session_id(event: AstrMessageEvent) -> str:
        unified = getattr(event, "unified_msg_origin", None)
        if unified:
            return str(unified)
        message_obj = getattr(event, "message_obj", None)
        return str(getattr(message_obj, "session_id", "") or getattr(message_obj, "group_id", "") or "default")

    @staticmethod
    def _user_id(event: AstrMessageEvent) -> str:
        try:
            return str(event.get_sender_id())
        except Exception:
            message_obj = getattr(event, "message_obj", None)
            sender = getattr(message_obj, "sender", None)
            return str(getattr(sender, "user_id", "") or getattr(sender, "id", "") or "unknown")

    @staticmethod
    def _user_name(event: AstrMessageEvent) -> str:
        try:
            return str(event.get_sender_name())
        except Exception:
            return SudokuSuperPlugin._user_id(event)

    @staticmethod
    def _mentioned_user_id(event: AstrMessageEvent) -> str | None:
        try:
            messages = event.get_messages()
        except Exception:
            messages = []
        for component in messages:
            name = component.__class__.__name__.lower()
            if name != "at":
                continue
            for attr in ("qq", "user_id", "uin", "target"):
                value = getattr(component, attr, None)
                if value:
                    return str(value)
        return None

    @staticmethod
    def _extract_user_id_from_text(text: str) -> str | None:
        match = re.search(r"\d{4,}", text or "")
        return match.group(0) if match else None

    def _config_int(self, key: str, default: int) -> int:
        try:
            return int(self.config.get(key, default))
        except Exception:
            return default

    def _config_float(self, key: str, default: float) -> float:
        try:
            return float(self.config.get(key, default))
        except Exception:
            return default

    def _config_bool(self, key: str, default: bool) -> bool:
        try:
            value = self.config.get(key, default)
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on", "开", "是"}
            return bool(value)
        except Exception:
            return default

    @staticmethod
    def _help_text() -> str:
        return (
            "🧩 Sudoku Super 指令\n"
            "/sudoku new <简单|中等|困难|地狱|恶魔> - 开始挑战\n"
            "/sudoku set <行> <列> <数字> - 填数，数字 0 或“清空”表示清除\n"
            "/sudoku board - 查看棋盘\n"
            "/sudoku check - 检查进度\n"
            "/sudoku hint [one_step|full_path] - 高级解题提示\n"
            "/sudoku advanced [one_step|full_path] - 高级解题模式\n"
            "/sudoku analyze [one_step|full_path] - 高级分析当前盘面\n"
            "/sudoku undo - 撤销上一步\n"
            "/sudoku giveup - 放弃并查看答案\n"
            "/sudoku answer - 查看答案并结束本局\n"
            "/sudoku rank [group|global] - 查看群内/全局排行榜\n"
            "/sudoku stats [@用户|global] - 查看统计\n"
            "活跃对局中可直接发送：1 2 9 或 s 1 2 9"
        )
