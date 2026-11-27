"""Regular expressions of a search run in a process that can be killed (FEA-0010).

Python's ``re`` has no time limit, and one unlucky pattern on one long text can run for hours; a
thread cannot be stopped. So the expressions of a search run in a separate process. It reports
each expression as soon as it is finished; when the time is up the process is killed, and the
parent keeps what was reported and says which expressions did not finish. The server never waits
longer than the budget, whatever the pattern is.

This module imports nothing heavy: a process started with ``spawn`` imports it again.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import re
import time

#: Longest text of a field that is handed to an expression; more is cut off.
TEXT_CAP = 50_000
#: How long the process may take to start (this is not part of the budget).
START_SECONDS = 20.0

# a job: (job id, pattern, re flags, fields)
Job = tuple[int, str, int, tuple[str, ...]]
# a row: (pk, title, body)
Row = tuple[int, str, str]


def _worker(connection, jobs: list[Job], rows: list[Row]) -> None:
    try:
        connection.send(("ready",))
        for job_id, pattern, flags, fields in jobs:
            compiled = re.compile(pattern, flags)
            matched: list[int] = []
            for pk, title, body in rows:
                for field in fields:
                    text = (title if field == "title" else body) or ""
                    if compiled.search(text[:TEXT_CAP]):
                        matched.append(pk)
                        break
            connection.send((job_id, matched))
        connection.send(None)
    finally:
        connection.close()


def _run(jobs: list[Job], rows: list[Row], seconds: float) -> tuple[dict[int, set[int]], list[int]]:
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(child, jobs, rows), daemon=True)
    process.start()
    child.close()
    done: dict[int, set[int]] = {}
    try:
        if not parent.poll(START_SECONDS):
            return done, [job[0] for job in jobs]
        parent.recv()  # ("ready",)
        deadline = time.monotonic() + seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not parent.poll(remaining):
                break
            message = parent.recv()
            if message is None:
                break
            done[message[0]] = set(message[1])
    except (EOFError, OSError):
        pass  # the process ended without finishing
    finally:
        if process.is_alive():
            process.kill()
        process.join(timeout=5)
        parent.close()
    return done, [job[0] for job in jobs if job[0] not in done]


async def run_regex_jobs(
    jobs: list[Job], rows: list[Row], seconds: float,
) -> tuple[dict[int, set[int]], list[int]]:
    """Run the jobs; returns the matches of the finished ones and the ids of the unfinished."""
    if not jobs:
        return {}, []
    return await asyncio.to_thread(_run, jobs, rows, seconds)
