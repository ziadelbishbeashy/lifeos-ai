"""Resolve the active LifeOS job backend."""

from __future__ import annotations

from flask import current_app

from jobs.base import JobExecutionError
from jobs.queue import InlineJobQueue, JobQueue, MemoryJobQueue


_memory_queue = MemoryJobQueue()


def get_job_queue() -> JobQueue:
    backend = str(current_app.config.get("JOB_BACKEND", "inline")).lower()
    if backend == "inline":
        return InlineJobQueue()
    if backend == "memory":
        return _memory_queue
    raise JobExecutionError(
        f'Unsupported job backend "{backend}". '
        "Use inline or memory until the Azure queue adapter is enabled."
    )
