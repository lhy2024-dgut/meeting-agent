from datetime import datetime
from typing import Any

from pydantic import BaseModel


class JobResult(BaseModel):
    meeting_id: int | None = None
    title: str | None = None
    output_path: str | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    progress_pct: int
    stage: str
    message: str
    created_at: datetime
    updated_at: datetime
    result: JobResult | None = None
    error: str | None = None


class CreateJobResponse(BaseModel):
    job_id: str
    status: str


class SceneOption(BaseModel):
    scene: str
    display_name: str
    description: str


class TemplateOption(BaseModel):
    name: str
    label: str
    has_docx: bool
    has_pdf: bool
    preview_path: str | None = None


class UploadMetadataResponse(BaseModel):
    scenes: list[SceneOption]
    templates: list[TemplateOption]
    output_formats: list[str]
    asr_models: list[str]
    chunk_strategies: list[dict[str, str]]
    transcription_modes: list[dict[str, str]]

