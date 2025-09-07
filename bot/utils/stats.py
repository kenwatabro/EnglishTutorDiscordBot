from __future__ import annotations

from datetime import datetime
from typing import Dict, Tuple

from .database import Database


async def record_result(word_id: int, correct: bool, when: datetime) -> None:
    db = await Database.get_instance()
    ts = when.isoformat()
    row = await db.fetchone("SELECT attempts, correct, ease FROM word_stats WHERE word_id = ?", (word_id,))
    if row is None:
        attempts = 1
        correct_cnt = 1 if correct else 0
        ease = 2.5 + (0.05 if correct else -0.15)
        ease = max(1.3, min(3.0, ease))
        await db.execute(
            "INSERT INTO word_stats(word_id, attempts, correct, last_seen, ease) VALUES (?, ?, ?, ?, ?)",
            (word_id, attempts, correct_cnt, ts, ease),
        )
        return
    attempts, correct_cnt, ease = row
    attempts += 1
    if correct:
        correct_cnt += 1
        ease += 0.05
    else:
        ease -= 0.15
    ease = max(1.3, min(3.0, ease))
    await db.execute(
        "UPDATE word_stats SET attempts = ?, correct = ?, last_seen = ?, ease = ? WHERE word_id = ?",
        (attempts, correct_cnt, ts, ease, word_id),
    )


async def fetch_stats_map(user_rows) -> Dict[int, Tuple[int, int, float]]:
    """Return map word_id -> (attempts, correct, ease)."""
    db = await Database.get_instance()
    ids = [row[0] for row in user_rows]
    if not ids:
        return {}
    # Build parameterized IN clause safely
    placeholders = ",".join(["?"] * len(ids))
    rows = await db.fetchall(
        f"SELECT word_id, attempts, correct, ease FROM word_stats WHERE word_id IN ({placeholders})",
        tuple(ids),
    )
    return {word_id: (attempts, correct, ease) for (word_id, attempts, correct, ease) in rows}

