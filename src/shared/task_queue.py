"""Simple async task tracker for background operations.

Used by L0_to_L4_consolidation to run dream cycles without blocking the MCP client.
Tasks auto-expire after 1 hour.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskInfo:
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    result: Any = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    duration_ms: float | None = None


class TaskTracker:
    """Track background asyncio tasks with status queries."""

    MAX_AGE_SECONDS = 3600  # Auto-cleanup after 1h

    def __init__(self):
        self._tasks: dict[str, TaskInfo] = {}
        self._asyncio_tasks: dict[str, asyncio.Task] = {}

    def schedule(self, coro, task_id: str | None = None) -> TaskInfo:
        """Schedule a coroutine as a background task. Returns immediately."""
        tid = task_id or str(uuid.uuid4())[:8]
        info = TaskInfo(task_id=tid, status=TaskStatus.PENDING)
        self._tasks[tid] = info

        async def _wrapper():
            info.status = TaskStatus.RUNNING
            t0 = time.time()
            try:
                result = await coro
                info.status = TaskStatus.COMPLETED
                info.result = result
            except Exception as e:
                info.status = TaskStatus.FAILED
                info.error = str(e)
            finally:
                info.completed_at = time.time()
                info.duration_ms = (info.completed_at - t0) * 1000

        task = asyncio.create_task(_wrapper())
        self._asyncio_tasks[tid] = task
        return info

    def get_status(self, task_id: str) -> TaskInfo | None:
        """Get current status of a task."""
        return self._tasks.get(task_id)

    def cleanup(self):
        """Remove tasks older than MAX_AGE_SECONDS."""
        now = time.time()
        expired = [
            tid for tid, info in self._tasks.items()
            if info.completed_at and (now - info.completed_at > self.MAX_AGE_SECONDS)
        ]
        for tid in expired:
            self._tasks.pop(tid, None)
            self._asyncio_tasks.pop(tid, None)


# Module-level singleton
_tracker: TaskTracker | None = None


def get_tracker() -> TaskTracker:
    global _tracker
    if _tracker is None:
        _tracker = TaskTracker()
    return _tracker
