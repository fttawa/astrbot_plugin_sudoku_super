from __future__ import annotations

from .models import DIFFICULTIES


def calculate_score(
    difficulty: str,
    elapsed_seconds: float,
    mistakes: int,
    *,
    time_bonus_ratio: float = 0.5,
    mistake_penalty_rate: float = 0.08,
) -> int:
    profile = DIFFICULTIES[difficulty]
    base = profile.base_score
    elapsed = max(0.0, elapsed_seconds)
    bonus_window = max(1, profile.target_seconds)
    time_bonus = max(0.0, (bonus_window - elapsed) / bonus_window) * base * time_bonus_ratio
    mistake_penalty = max(0, mistakes) * base * mistake_penalty_rate
    return max(1, int(round(base + time_bonus - mistake_penalty)))


def format_duration(seconds: float) -> str:
    seconds = int(max(0, round(seconds)))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}小时{minutes:02d}分{sec:02d}秒"
    if minutes:
        return f"{minutes}分{sec:02d}秒"
    return f"{sec}秒"
