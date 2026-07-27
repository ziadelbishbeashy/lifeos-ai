"""Development worker for jobs held in the in-memory queue.

The public architecture will replace this backend with Azure Service Bus. This
runner establishes the worker boundary without pretending that memory queues
can coordinate multiple production processes.
"""

from __future__ import annotations

import time

from app import create_app
from jobs.registry import get_job_handler
from jobs.service import get_job_queue


def main() -> None:
    app = create_app()
    with app.app_context():
        queue = get_job_queue()
        pop = getattr(queue, "pop", None)
        if pop is None:
            raise RuntimeError(
                "Set JOB_BACKEND=memory to run the development worker."
            )
        app.logger.info("LifeOS development job worker started.")
        while True:
            job = pop()
            if job is None:
                time.sleep(1)
                continue
            handler = get_job_handler(job.name)
            if handler is None:
                app.logger.error("No handler for job %s.", job.name)
                continue
            try:
                handler(job.payload)
                app.logger.info("Completed job %s (%s).", job.name, job.id)
            except Exception:
                app.logger.exception("Job %s (%s) failed.", job.name, job.id)


if __name__ == "__main__":
    main()
