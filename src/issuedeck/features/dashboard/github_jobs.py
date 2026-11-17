"""Background jobs for the GitHub page (FEA-0008).

An export or an import talks to GitHub several times and can take seconds. The dashboard starts
it as a job and answers at once; the page then asks for the job's progress (the steps done so
far, the elapsed time) and, when it has finished, its result. That keeps the page from
reloading and lets it show what is happening.

Jobs live in memory only. They are for showing progress; the work itself is recorded the usual
way (the repository, the settings audit log), so a restart loses nothing but the progress view.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from issuedeck.core.errors import IssueDeckError

log = logging.getLogger(__name__)

MAX_JOBS = 100
MAX_AGE_SECONDS = 3600


class JobBusy(Exception):
    """The same kind of work is already running for the same target."""


@dataclass
class Job:
    id: str
    kind: str
    key: str
    started: float = field(default_factory=time.monotonic)
    finished: float | None = None
    state: str = "running"  # running | done | error
    steps: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    result: Any = None
    error: str | None = None
    status: int = 200
    task: asyncio.Task | None = field(default=None, repr=False)

    def step(self, step: str, /, **params: Any) -> None:
        """Report a step; usable as the ``progress`` callback of the services."""
        self.steps.append((step, params))

    @property
    def elapsed(self) -> float:
        return (self.finished or time.monotonic()) - self.started


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def start(
        self, kind: str, key: str, work: Callable[[Job], Awaitable[Any]],
    ) -> Job:
        """Run ``work(job)`` in the background. Refuses a second job of the same kind and key."""
        self._prune()
        if key and any(
            j.state == "running" and j.kind == kind and j.key == key
            for j in self._jobs.values()
        ):
            raise JobBusy(f"{kind} for {key} is already running")
        job = Job(id=secrets.token_hex(8), kind=kind, key=key)
        self._jobs[job.id] = job
        job.task = asyncio.create_task(self._run(job, work))
        return job

    async def _run(self, job: Job, work: Callable[[Job], Awaitable[Any]]) -> None:
        try:
            job.result = await work(job)
            job.state = "done"
        except IssueDeckError as exc:
            job.error, job.status, job.state = exc.message, exc.http_status, "error"
        except Exception:  # noqa: BLE001 - a job must never take the server down
            log.exception("GitHub job %s (%s) failed", job.id, job.kind)
            job.error, job.status, job.state = "an unexpected error occurred", 500, "error"
        finally:
            job.finished = time.monotonic()

    def _prune(self) -> None:
        now = time.monotonic()
        for job_id in [
            j.id for j in self._jobs.values()
            if j.finished is not None and now - j.finished > MAX_AGE_SECONDS
        ]:
            del self._jobs[job_id]
        finished = sorted(
            (j for j in self._jobs.values() if j.finished is not None),
            key=lambda j: j.finished or 0.0,
        )
        while len(self._jobs) > MAX_JOBS and finished:
            del self._jobs[finished.pop(0).id]
