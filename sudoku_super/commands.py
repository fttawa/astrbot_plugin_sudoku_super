from __future__ import annotations

import re

from .models import Move

_MOVE_RE = re.compile(
    r"^(?:s|set|填|填入)?\s*([1-9])[\s,，]+([1-9])[\s,，]+([0-9]|清空|空|删|删除)\s*$",
    re.IGNORECASE,
)
_R1C1_RE = re.compile(r"^r([1-9])c([1-9])\s*=?\s*([0-9]|清空|空|删|删除)\s*$", re.IGNORECASE)


def parse_move_text(text: str) -> Move | None:
    raw = (text or "").strip()
    if not raw or raw.startswith("/"):
        return None
    match = _MOVE_RE.fullmatch(raw) or _R1C1_RE.fullmatch(raw)
    if not match:
        return None
    row = int(match.group(1)) - 1
    col = int(match.group(2)) - 1
    value_raw = match.group(3)
    value = 0 if value_raw in {"清空", "空", "删", "删除"} else int(value_raw)
    return Move(row=row, col=col, value=value)


def parse_command_value(raw: str | int) -> int:
    value = str(raw).strip()
    if value in {"清空", "空", "删", "删除"}:
        return 0
    if not value.isdigit():
        raise ValueError("数字必须是 0-9，或使用“清空”")
    digit = int(value)
    if digit < 0 or digit > 9:
        raise ValueError("数字必须是 0-9")
    return digit


def normalize_rank_scope(raw: str | None) -> str:
    value = (raw or "group").strip().casefold()
    if value in {"group", "g", "群", "群内", "本群", "session"}:
        return "group"
    if value in {"global", "all", "世界", "全局", "总榜"}:
        return "global"
    raise ValueError("排行榜范围只能是 group/群内 或 global/全局")
