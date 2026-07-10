"""A controlled, recoverable worker for persistent V2 knowledge jobs.

The HTTP layer must only enqueue a job.  This worker is the process-local
consumer that claims durable leases and records an explicit terminal state.
It deliberately owns no parsing or compilation logic; concrete handlers are
injected so they can be tested and evolved independently.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.db.sqlite_store import SqliteStore
from app.schemas.knowledge_jobs import KnowledgeJob

KnowledgeJobHandler = Callable[[KnowledgeJob], Awaitable[None]]


@dataclass(frozen=True)
class KnowledgeJobExecutionError(Exception):
    """A handler error with a stable, user-visible retry decision."""

    detail: str
    code: str = "knowledge_job_failed"
    retryable: bool = True

    def __str__(self) -> str:
        return self.detail


class KnowledgeJobWorker:
    """Claim and execute jobs serially for the SQLite MVP queue.

    A worker instance processes one job at a time.  The store's lease guards
    against duplicate work after a restart; cancellation intentionally leaves
    the lease in place so a later worker can reclaim it after expiry.
    """

    def __init__(
        self,
        store: SqliteStore,
        *,
        worker_id: str,
        handlers: dict[str, KnowledgeJobHandler],
        lease_seconds: int = 120,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self._store = store
        self._worker_id = worker_id
        self._handlers = handlers
        self._lease_seconds = lease_seconds
        self._poll_interval_seconds = poll_interval_seconds

    async def run_once(self) -> KnowledgeJob | None:
        """Claim at most one job and persist its result.

        ``None`` means there was no eligible work.  A handler may raise
        :class:`KnowledgeJobExecutionError` to select a visible retryable or
        terminal failure.  Unexpected exceptions are also visible failures,
        but remain retryable because infrastructure faults should not discard
        a student's course material.
        """
        job = await asyncio.to_thread(
            self._store.claim_next_knowledge_job,
            self._worker_id,
            self._lease_seconds,
        )
        if job is None:
            return None

        handler = self._handlers.get(job.job_type)
        if handler is None:
            await asyncio.to_thread(
                self._store.fail_knowledge_job,
                job.course_id,
                job.job_id,
                self._worker_id,
                f"No handler is registered for knowledge job type {job.job_type!r}",
                retryable=False,
                error_code="unsupported_knowledge_job_type",
            )
            return job

        try:
            await handler(job)
        except asyncio.CancelledError:
            # Do not race shutdown against a future worker.  The durable lease
            # will expire and the job can be safely reclaimed.
            raise
        except KnowledgeJobExecutionError as exc:
            await asyncio.to_thread(
                self._store.fail_knowledge_job,
                job.course_id,
                job.job_id,
                self._worker_id,
                exc.detail,
                retryable=exc.retryable,
                error_code=exc.code,
            )
        except Exception as exc:
            await asyncio.to_thread(
                self._store.fail_knowledge_job,
                job.course_id,
                job.job_id,
                self._worker_id,
                f"Unexpected knowledge job failure: {exc}",
                retryable=True,
                error_code="unexpected_knowledge_job_failure",
            )
        else:
            await asyncio.to_thread(
                self._store.complete_knowledge_job,
                job.course_id,
                job.job_id,
                self._worker_id,
            )
        return job

    async def run(self, stop_event: asyncio.Event) -> None:
        """Continuously consume durable work until the owner requests stop."""
        while not stop_event.is_set():
            job = await self.run_once()
            if job is None:
                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=self._poll_interval_seconds
                    )
                except TimeoutError:
                    continue
