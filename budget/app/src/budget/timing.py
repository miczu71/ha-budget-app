"""Pomiar czasu kroków żądania do nagłówka `Server-Timing` (poza żądaniem nic nie zapisuje)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_timings: ContextVar[dict[str, float] | None] = ContextVar("timings", default=None)


@contextmanager
def timed(step: str) -> Iterator[None]:
    """Czas kroku żądania (ms) do nagłówka `Server-Timing`; poza żądaniem nic nie zapisuje."""
    start = time.perf_counter()
    try:
        yield
    finally:
        steps = _timings.get()
        if steps is not None:
            steps[step] = steps.get(step, 0.0) + (time.perf_counter() - start) * 1000


def start_timings() -> dict[str, float]:
    steps: dict[str, float] = {}
    _timings.set(steps)
    return steps


def server_timing(steps: dict[str, float], total_ms: float) -> str:
    parts = {"total": total_ms, **steps}
    return ", ".join(f"{name};dur={ms:.0f}" for name, ms in parts.items())
