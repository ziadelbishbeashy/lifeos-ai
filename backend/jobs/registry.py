"""In-process job-handler registry for local development and tests."""

from __future__ import annotations

from jobs.base import JobHandler


_HANDLERS: dict[str, JobHandler] = {}


def register_job(name: str, handler: JobHandler) -> None:
    if not name:
        raise ValueError("Job name is required.")
    _HANDLERS[name] = handler


def get_job_handler(name: str) -> JobHandler | None:
    return _HANDLERS.get(name)
