"""Provider-independent queue foundation for LifeOS background work."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from typing import Any

from jobs.base import Job, JobExecutionError
from jobs.registry import get_job_handler


class JobQueue(ABC):
    @abstractmethod
    def enqueue(self, name: str, payload: dict[str, Any]) -> Job:
        """Create and enqueue a job."""


class InlineJobQueue(JobQueue):
    """Execute immediately in local development; never use for heavy public jobs."""

    def enqueue(self, name: str, payload: dict[str, Any]) -> Job:
        job = Job(name=name, payload=dict(payload))
        handler = get_job_handler(name)
        if handler is None:
            raise JobExecutionError(f'No handler registered for job "{name}".')
        try:
            handler(job.payload)
        except Exception as error:
            raise JobExecutionError(f'Job "{name}" failed.') from error
        return job


class MemoryJobQueue(JobQueue):
    """Small deterministic queue for tests and architecture development."""

    def __init__(self):
        self.jobs: deque[Job] = deque()

    def enqueue(self, name: str, payload: dict[str, Any]) -> Job:
        job = Job(name=name, payload=dict(payload))
        self.jobs.append(job)
        return job

    def pop(self) -> Job | None:
        return self.jobs.popleft() if self.jobs else None
