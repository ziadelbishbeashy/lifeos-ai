"""Background-job foundation tests."""

from jobs.queue import MemoryJobQueue


def test_memory_job_queue_preserves_payload():
    queue = MemoryJobQueue()
    queued = queue.enqueue("document.extract", {"document_id": 4})
    popped = queue.pop()
    assert popped == queued
    assert popped.payload["document_id"] == 4
