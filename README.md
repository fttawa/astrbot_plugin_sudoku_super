# Sudoku Super for AstrBot

AstrBot 数独插件：支持题目挑战、简单/中等/困难/地狱/恶魔五档难度生成、HTML 棋盘图片、用户解题、撤销、检查、放弃/答案和群内/全局排行榜。

## 指令

- `/sudoku new <简单|中等|困难|地狱|恶魔>`：开始挑战
- `/sudoku set <行> <列> <数字>`：填数，`0` 或 `清空` 表示清除非题目格
- `/sudoku board`：查看当前棋盘
- `/sudoku check`：检查进度
- `/sudoku hint [one_step|full_path]`：WASM 高级解题提示
- `/sudoku advanced [one_step|full_path]`：进入高级解题模式并分析当前盘面
- `/sudoku analyze [one_step|full_path]`：高级分析当前盘面
- `/sudoku undo`：撤销上一步
- `/sudoku giveup`：放弃并查看答案，不计入排行榜
- `/sudoku answer`：查看答案并结束本局
- `/sudoku rank [group|global]`：查看群内/全局排行榜
- `/sudoku stats [@用户|global]`：查看统计

活跃对局中可直接发送 `1 2 9`、`s 1 2 9` 或 `1,2,9` 快速填数。

无论填数正确、错误、重复、清空还是尝试修改题目格，插件都会在文字反馈后发送当前棋盘图片。

## 配置

- `show_candidates`：是否在棋盘图片空格内显示候选数。
- `candidate_source`：候选数来源，`auto` 优先使用 WASM 高级引擎，失败后降级本地候选数；`local` 只使用本地基础候选数；`wasm` 使用高级引擎。
- `advanced_solver_enabled`：是否启用 WASM 高级解题模式。
- `advanced_solver_sdk_dir`：本机外部 WASM SDK 目录；插件仓库不内置 SDK。
- `node_executable`：Node.js 可执行文件，默认 `node`。

## 实现摘要

生成器采用随机完整盘生成、中心对称/散布挖空、唯一解校验和难度评分过滤。排行榜与活跃对局存储在 AstrBot 插件数据目录下的 SQLite 数据库。

高级解题模式仅在配置了外部 WASM SDK 目录且运行环境存在 Node.js 时启用；不可用时会自动降级为基础候选数提示。
