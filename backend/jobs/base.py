"""Background-job contracts used by Document Brain and future agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4


@dataclass(frozen=True)
class Job:
    name: str
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=datetime.utcnow)


class JobExecutionError(RuntimeError):
    """Raised when a registered background job fails."""


JobHandler = Callable[[dict[str, Any]], Any]
