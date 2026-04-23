"""Timing utilities for MCP tool debugging.

Provides a decorator and context manager for measuring latency
inside MCP tool calls. Only active when MCP_DEBUG=1.
"""
from __future__ import annotations

import os
import time
from functools import wraps
from typing import Any, Callable


DEBUG = os.getenv("MCP_DEBUG", "0") == "1"


class Timer:
    """Accumulate timing for multiple phases."""

    def __init__(self):
        self.phases: dict[str, float] = {}
        self._start: float | None = None
        self._current_phase: str | None = None

    def start(self, phase: str) -> "Timer":
        self._current_phase = phase
        self._start = time.perf_counter()
        return self

    def stop(self) -> "Timer":
        if self._start is not None and self._current_phase is not None:
            elapsed = (time.perf_counter() - self._start) * 1000
            self.phases[self._current_phase] = round(elapsed, 1)
            self._start = None
            self._current_phase = None
        return self

    def to_dict(self) -> dict[str, Any]:
        if not self.phases:
            return {}
        return {
            "_debug": {
                "phases_ms": self.phases,
                "total_ms": round(sum(self.phases.values()), 1),
            }
        }


def timed(func: Callable | None = None, *, phases: list[str] | None = None):
    """Decorator to add timing to MCP tool functions.

    Only adds _debug field when MCP_DEBUG=1.
    The decorated function receives a `timer` keyword argument.

    Usage:
        @timed
        async def my_tool(content: str, timer: Timer = None) -> dict:
            t = timer or Timer()
            t.start("embed")
            vec = await safe_embed(content)
            t.stop()
            result = {"status": "stored", ...}
            result.update(t.to_dict())
            return result
    """
    def decorator(fn: Callable) -> Callable:
        if not DEBUG:
            return fn

        @wraps(fn)
        async def wrapper(*args, **kwargs):
            timer = Timer()
            kwargs.setdefault("timer", timer)
            result = await fn(*args, **kwargs)
            if isinstance(result, dict):
                result.update(timer.to_dict())
            return result

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator
