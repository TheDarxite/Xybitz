"""
In-memory activity ring buffer.
Captures key pipeline events for display in the admin console.
Thread/async safe enough for single-worker use. Max 200 entries (oldest auto-dropped).
"""
from collections import deque
from datetime import datetime, timezone
from typing import TypedDict


class ActivityEntry(TypedDict):
    time: str      # HH:MM:SS UTC
    level: str     # "info" | "success" | "error" | "warn"
    category: str  # "fetch" | "summarise" | "retry" | "system"
    message: str


ACTIVITY_LOG: deque[ActivityEntry] = deque(maxlen=200)


def log_activity(level: str, category: str, message: str) -> None:
    ACTIVITY_LOG.appendleft(
        ActivityEntry(
            time=datetime.now(timezone.utc).strftime("%H:%M:%S"),
            level=level,
            category=category,
            message=message,
        )
    )
