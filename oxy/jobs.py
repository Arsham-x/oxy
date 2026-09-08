"""
OXY Jobs — Background job manager with isolated execution and shared telemetry.

Runs long-running commands in the background while the REPL remains responsive:
  - Each job runs in its own subprocess with captured stdout/stderr
  - Poll via status(), list via list_jobs(), cancel via cancel()
  - Thread-safe with a shared lock
  - Job events flow into the observability EventLogger
"""

from __future__ import annotations

import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Job:
    job_id: str
    command: str
    status: str = "running"  # running | completed | failed | cancelled
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    returncode: int | None = None
    output: str = ""
    _proc: subprocess.Popen | None = field(default=None, repr=False, compare=False)


class JobManager:
    """Manages concurrent background shell jobs with isolated execution."""

    def __init__(self, max_jobs: int = 8):
        self.max_jobs = max_jobs
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}

    def submit(self, command: str, timeout: int = 300) -> Job:
        """Submit a shell command as a background job."""
        with self._lock:
            active = sum(1 for j in self._jobs.values() if j.status == "running")
            if active >= self.max_jobs:
                raise RuntimeError(f"Job queue full ({self.max_jobs} running). Cancel or wait for a job.")

            job_id = uuid.uuid4().hex[:8]
            try:
                proc = subprocess.Popen(
                    command,
                    shell=True,
                    executable="/bin/bash",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=".",
                )
            except Exception as e:
                raise RuntimeError(f"Failed to launch background job: {e}")

            job = Job(job_id=job_id, command=command, _proc=proc)
            self._jobs[job_id] = job

        # Watcher thread flips status when process completes
        watcher = threading.Thread(target=self._watch, args=(job_id, timeout), daemon=True)
        watcher.start()
        return job

    def _watch(self, job_id: str, timeout: int):
        job = self._jobs.get(job_id)
        if not job or not job._proc:
            return
        try:
            out, _ = job._proc.communicate(timeout=timeout)
            job.output = out or ""
            job.returncode = job._proc.returncode
            job.status = "completed" if job.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            try:
                job._proc.kill()
            except Exception:
                pass
            job.output = (job.output or "") + f"\n[Job timed out after {timeout}s and was killed]"
            job.status = "failed"
            job.returncode = -1
        finally:
            job.finished_at = time.time()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def status(self, job_id: str) -> dict[str, Any]:
        job = self.get(job_id)
        if not job:
            return {"found": False, "job_id": job_id}
        if job.status == "running" and job._proc:
            # Refresh liveness without blocking
            rc = job._proc.poll()
            if rc is not None:
                try:
                    out, _ = job._proc.communicate(timeout=1)
                    job.output = (job.output or "") + (out or "")
                except Exception:
                    pass
                job.returncode = rc
                job.status = "completed" if rc == 0 else "failed"
                job.finished_at = time.time()
        return {
            "found": True,
            "job_id": job.job_id,
            "command": job.command,
            "status": job.status,
            "returncode": job.returncode,
            "output_tail": (job.output or "")[-2000:],
            "elapsed": round((job.finished_at or time.time()) - job.created_at, 1),
        }

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())
        return [
            {
                "job_id": j.job_id,
                "command": j.command[:80],
                "status": j.status,
                "returncode": j.returncode,
                "elapsed": round((j.finished_at or time.time()) - j.created_at, 1),
            }
            for j in jobs
        ]

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if not job or job.status != "running":
            return False
        try:
            if job._proc:
                job._proc.terminate()
                try:
                    job._proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    job._proc.kill()
            job.status = "cancelled"
            job.finished_at = time.time()
            return True
        except Exception:
            return False

    def get_output(self, job_id: str, tail: int = 2000) -> str:
        job = self.get(job_id)
        if not job:
            return f"No job found with id '{job_id}'."
        self.status(job_id)  # refresh
        return (job.output or "(no output yet)")[-tail:]
