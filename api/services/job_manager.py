from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable


@dataclass
class JobState:
    job_id: str
    job_type: str
    status: str = "pending"
    progress_pct: int = 0
    stage: str = "queued"
    message: str = "任务已创建"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    result: dict[str, Any] | None = None
    error: str | None = None


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()

    def create_job(self, job_type: str) -> JobState:
        job = JobState(job_id=uuid.uuid4().hex, job_type=job_type)
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get_job(self, job_id: str) -> JobState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress_pct: int | None = None,
        stage: str | None = None,
        message: str | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> JobState | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            if status is not None:
                job.status = status
            if progress_pct is not None:
                job.progress_pct = max(0, min(progress_pct, 100))
            if stage is not None:
                job.stage = stage
            if message is not None:
                job.message = message
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error
            job.updated_at = datetime.now()
            return job

    def run_in_thread(
        self,
        job_id: str,
        target: Callable[[], dict[str, Any] | None],
    ) -> None:
        def runner() -> None:
            self.update_job(
                job_id,
                status="running",
                progress_pct=1,
                stage="starting",
                message="开始处理",
            )
            try:
                result = target() or {}
                self.update_job(
                    job_id,
                    status="succeeded",
                    progress_pct=100,
                    stage="done",
                    message="处理完成",
                    result=result,
                )
            except Exception as exc:
                self.update_job(
                    job_id,
                    status="failed",
                    stage="failed",
                    message="处理失败",
                    error=str(exc),
                )

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()


job_manager = JobManager()
