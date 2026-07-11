from fastapi import APIRouter, HTTPException

from api.schemas.jobs import JobResult, JobStatusResponse
from api.services.job_manager import job_manager

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")

    result = JobResult(**job.result) if job.result else None
    return JobStatusResponse(
        job_id=job.job_id,
        job_type=job.job_type,
        status=job.status,
        progress_pct=job.progress_pct,
        stage=job.stage,
        message=job.message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        result=result,
        error=job.error,
    )

