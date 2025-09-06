from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Tuple
import re

from .database import Database

DEFAULT_INTERVALS = [1, 4, 10, 17, 30, 60]


def parse_pairs(text: str) -> List[Tuple[str, str]]:
    """Parse pairs like "word:meaning" separated by newlines, commas, or semicolons.

    Accepts common separators: newline, comma, Japanese comma (、)， semicolon, Japanese colon（：）.
    Returns list of (word, meaning) with whitespace trimmed; invalid lines are ignored.
    """
    if not text:
        return []
    # Split by newlines or separators ; , 、 ，
    chunks = re.split(r"[\n;；]+", text)
    pairs: List[Tuple[str, str]] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        # Split by colon or space after word
        m = re.match(r"^(.*?)[:：，,\s]+(.+)$", chunk)
        if not m:
            continue
        word = m.group(1).strip()
        meaning = m.group(2).strip()
        if word and meaning:
            pairs.append((word, meaning))
    return pairs


async def insert_pairs(user_id: int, pairs: Iterable[Tuple[str, str]], added_at: datetime, intervals: Iterable[int] = DEFAULT_INTERVALS) -> int:
    """Insert pairs for a user; returns count inserted."""
    db = await Database.get_instance()
    count = 0
    intervals_remaining = ",".join(map(str, list(intervals)[:5]))  # keep alignment with existing schema
    ts = added_at.isoformat()
    for word, meaning in pairs:
        await db.execute(
            """
            INSERT INTO words (user_id, word, meaning, added_at, intervals_remaining)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, word, meaning, ts, intervals_remaining),
        )
        count += 1
    return count


async def fetch_user_words(user_id: int):
    db = await Database.get_instance()
    return await db.fetchall(
        "SELECT id, word, meaning, added_at FROM words WHERE user_id = ? ORDER BY id ASC",
        (user_id,),
    )


def compute_due_today(rows, now: datetime, intervals: Iterable[int] = DEFAULT_INTERVALS):
    """Return list of words due today based on days since added."""
    intervals_set = set(intervals)
    due = []
    for _id, word, meaning, added_at in rows:
        try:
            added_time = datetime.fromisoformat(added_at)
        except Exception:
            continue
        days = (now.date() - added_time.date()).days
        if days in intervals_set:
            due.append((_id, word, meaning))
    return due


def compute_progress(rows, now: datetime, intervals: Iterable[int] = DEFAULT_INTERVALS):
    """Compute simple progress summary for a user.

    Returns dict with total, due_today, stage_counts.
    stage is max index where interval <= days since added, clamped to [0..len(intervals)].
    """
    ints = list(intervals)
    total = len(rows)
    due_today = len(compute_due_today(rows, now, intervals=ints))
    stage_counts = [0] * (len(ints) + 1)  # final bucket = beyond last interval
    for _id, word, meaning, added_at in rows:
        try:
            added_time = datetime.fromisoformat(added_at)
        except Exception:
            continue
        days = (now.date() - added_time.date()).days
        stage = 0
        for idx, iv in enumerate(ints, start=1):
            if days >= iv:
                stage = idx
        stage_counts[stage] += 1
    return {
        "total": total,
        "due_today": due_today,
        "stage_counts": stage_counts,
        "intervals": ints,
    }

