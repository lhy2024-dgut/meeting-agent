from datetime import datetime
from pathlib import Path

import config
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.deps import get_current_user, get_meeting_repository
from api.schemas.jobs import CreateJobResponse
from api.schemas.meetings import (
    HtmlSummaryGenerateRequest,
    HtmlSummaryResponse,
    MeetingDetail,
    MeetingListResponse,
    MeetingMetaResponse,
    MeetingMutationResponse,
    MeetingProjectUpdateRequest,
    MeetingSummary,
    MeetingTermsResponse,
    TranscriptResponse,
    TranscriptSegment,
)
from api.schemas.todos import TodoItemResponse
from api.services.job_manager import job_manager
from chains.export_chain import get_template_path
from chains.html_summary_chain import HtmlSummaryChain, get_html_summary_path
from chains.minutes_chain import (
    MinutesChain,
    PLACEHOLDER_NO_ACTION,
    PLACEHOLDER_NO_RESOLUTION,
)
from db.repository import MeetingRepository
from prompts.templates import PromptTemplateLoader
from rag.retriever import get_retriever
from services.file_service import FileService
from services.meeting_service import ASR_MODEL_SENSEVOICE, MeetingService
from services.terms_service import load_terms, save_terms, truncate_terms
from services.todo_service import TodoService, parse_action_items_text

router = APIRouter(prefix="/api/meetings", tags=["meetings"])

_AUDIO_MEDIA_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
    ".mp4": "video/mp4",
}


class MeetingRegenerateRequest(BaseModel):
    terms: list[str] | None = None


def _format_duration_label(category: str | None) -> str:
    return config.DURATION_LABELS.get(category or "", "未知")


def _format_environment_label(environment: str | None) -> str:
    return config.ENV_LABELS.get(environment or "", "未知")


def _count_action_items(action_items_text: str | None) -> int:
    return len(parse_action_items_text(action_items_text))


def _count_resolutions(resolutions_text: str | None) -> int:
    if not resolutions_text:
        return 0
    return max(0, resolutions_text.count("\n"))


def _build_duration_display(total_seconds: float) -> str:
    total_seconds = max(total_seconds, 0)
    total_minutes = int(total_seconds // 60)
    if total_minutes < 60:
        return f"{total_minutes} 分钟"
    return f"{total_minutes // 60} 小时 {total_minutes % 60} 分钟"


def _serialize_summary(meeting) -> MeetingSummary:
    return MeetingSummary(
        id=meeting.id,
        title=meeting.title,
        created_at=meeting.created_at,
        updated_at=meeting.updated_at,
        duration_category=meeting.duration_category or "",
        duration_label=_format_duration_label(meeting.duration_category),
        environment=meeting.environment or "",
        environment_label=_format_environment_label(meeting.environment),
        short_summary=meeting.short_summary or "",
        project_name=meeting.project_name or "",
        action_item_count=_count_action_items(meeting.action_items_text),
        resolution_count=_count_resolutions(meeting.resolutions_text),
        is_private=bool(meeting.is_private),
    )


def _serialize_segments(transcriptions) -> list[TranscriptSegment]:
    # 按时间戳升序（说话人识别返回的分句顺序不保证按时间）
    ordered = sorted(
        transcriptions,
        key=lambda item: (item.start_time or 0.0, item.end_time or 0.0),
    )
    return [
        TranscriptSegment(
            id=item.id,
            text=item.text or "",
            timestamp=item.timestamp or 0.0,
            start_time=item.start_time or 0.0,
            end_time=item.end_time or 0.0,
            speaker=item.speaker or "",
        )
        for item in ordered
    ]


def _save_uploaded_file(file_service: FileService, upload_file: UploadFile) -> tuple[str, str, str]:
    file_bytes = upload_file.file.read()
    suffix = Path(upload_file.filename or "").suffix.lower()
    category = "video" if suffix in config.ALLOWED_VIDEO_EXTENSIONS else "audio"
    timestamped_name = upload_file.filename or f"upload{suffix or '.bin'}"

    class InMemoryUpload:
        def __init__(self, name: str, payload: bytes) -> None:
            self.name = name
            self._payload = payload

        def getvalue(self) -> bytes:
            return self._payload

    saved_path, file_hash = file_service.save_uploaded(
        InMemoryUpload(timestamped_name, file_bytes),
        category,
    )
    return saved_path, file_hash, suffix


def _parse_terms(terms_raw: str | None) -> list[str]:
    if not terms_raw:
        return []
    parts = []
    normalized = terms_raw.replace(",", "\n").replace("，", "\n")
    for line in normalized.splitlines():
        stripped = line.strip()
        if stripped:
            parts.append(stripped)
    kept, _ = truncate_terms(parts)
    return kept


def _get_owned_meeting(repo: MeetingRepository, meeting_id: int, user_id: int):
    meeting = repo.get_meeting_by_id(meeting_id, user_id=user_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting


def _get_meeting_todos(repo: MeetingRepository, user_id: int, meeting_id: int):
    service = TodoService(repo)
    items = service.list_todos(user_id, meeting_id=meeting_id)
    return [
        TodoItemResponse(
            id=item.id,
            user_id=item.user_id,
            meeting_id=item.meeting_id,
            content=item.content,
            assignee=item.assignee,
            due_date=item.due_date,
            status=item.status,
            priority=item.priority,
            source=item.source,
            is_user_modified=item.is_user_modified,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in items
    ]


@router.get("", response_model=MeetingListResponse)
def list_meetings(
    page: int = Query(default=0, ge=0),
    page_size: int = Query(default=10, ge=1, le=50),
    search: str = "",
    duration: str = "",
    environment: str = "",
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> MeetingListResponse:
    duration_map = {
        "short": "短会 (<5min)",
        "medium": "中等 (5-30min)",
        "long": "长会 (>30min)",
    }
    environment_map = {
        "quiet": "安静",
        "noisy": "嘈杂",
        "multi_speaker": "多人",
        "unknown": "未知",
    }

    meetings, total = repo.get_meetings_paginated(
        page=page,
        page_size=page_size,
        search=search,
        dur_filter=duration_map.get(duration, "全部"),
        env_filter=environment_map.get(environment, "全部"),
        user_id=current_user.id,
    )
    items = [_serialize_summary(meeting) for meeting in meetings]
    return MeetingListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=max(1, (total + page_size - 1) // page_size),
    )


@router.get("/{meeting_id}", response_model=MeetingDetail)
def get_meeting(
    meeting_id: int,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> MeetingDetail:
    meeting = _get_owned_meeting(repo, meeting_id, current_user.id)
    todo_service = TodoService(repo)
    todo_service.sync_meeting_todos(
        current_user.id,
        meeting.id,
        meeting.action_items_text or "",
        replace=False,
    )
    todos = _get_meeting_todos(repo, current_user.id, meeting.id)
    segments = _serialize_segments(meeting.transcriptions)
    total_seconds = max((segment.end_time for segment in segments), default=0.0)
    return MeetingDetail(
        id=meeting.id,
        title=meeting.title,
        created_at=meeting.created_at,
        updated_at=meeting.updated_at,
        date_text=meeting.created_at.strftime("%Y-%m-%d %H:%M") if meeting.created_at else "",
        duration_category=meeting.duration_category or "",
        duration_label=_format_duration_label(meeting.duration_category),
        environment=meeting.environment or "",
        environment_label=_format_environment_label(meeting.environment),
        duration_seconds=total_seconds,
        duration_display=_build_duration_display(total_seconds),
        minutes_text=meeting.minutes_text or "",
        action_items_text=meeting.action_items_text or "",
        resolutions_text=meeting.resolutions_text or "",
        short_summary=meeting.short_summary or "",
        project_name=meeting.project_name or "",
        action_item_count=len(todos),
        resolution_count=_count_resolutions(meeting.resolutions_text),
        transcript_count=len(segments),
        is_private=bool(meeting.is_private),
        todos=todos,
    )


@router.get("/{meeting_id}/meta", response_model=MeetingMetaResponse)
def get_meeting_meta(
    meeting_id: int,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> MeetingMetaResponse:
    """轻量元信息：只返回是否私密等，不含纪要/转录正文。

    供详情页在渲染前判断是否需要密码门，避免把私密正文下发到 HTML。
    """
    meeting = _get_owned_meeting(repo, meeting_id, current_user.id)
    return MeetingMetaResponse(
        id=meeting.id,
        title=meeting.title,
        date_text=meeting.created_at.strftime("%Y-%m-%d %H:%M") if meeting.created_at else "",
        is_private=bool(meeting.is_private),
    )


@router.get("/{meeting_id}/transcript", response_model=TranscriptResponse)
def get_transcript(
    meeting_id: int,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> TranscriptResponse:
    meeting = _get_owned_meeting(repo, meeting_id, current_user.id)
    segments = _serialize_segments(meeting.transcriptions)
    full_text = " ".join(segment.text for segment in segments)
    updated_at = meeting.updated_at or meeting.created_at or datetime.now()
    return TranscriptResponse(
        meeting_id=meeting_id,
        updated_at=updated_at,
        full_text=full_text,
        segments=segments,
    )


@router.get("/{meeting_id}/audio")
def get_meeting_audio(
    meeting_id: int,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> FileResponse:
    meeting = _get_owned_meeting(repo, meeting_id, current_user.id)
    if not meeting.audio_path:
        raise HTTPException(status_code=404, detail="Original audio file is missing")
    audio_path = Path(meeting.audio_path)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Original audio file is missing")

    media_type = _AUDIO_MEDIA_TYPES.get(audio_path.suffix.lower(), "application/octet-stream")
    # FileResponse 支持 Range 请求，便于前端拖动进度条时按需加载
    return FileResponse(path=str(audio_path), media_type=media_type, filename=audio_path.name)


@router.get("/{meeting_id}/html-summary", response_model=HtmlSummaryResponse)
def get_html_summary(
    meeting_id: int,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> HtmlSummaryResponse:
    _get_owned_meeting(repo, meeting_id, current_user.id)
    path = get_html_summary_path(meeting_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="HTML summary not found")

    return HtmlSummaryResponse(
        meeting_id=meeting_id,
        html=path.read_text(encoding="utf-8"),
        file_name=path.name,
        updated_at=datetime.fromtimestamp(path.stat().st_mtime),
    )


@router.post("/{meeting_id}/html-summary/generate", response_model=HtmlSummaryResponse)
def generate_html_summary(
    meeting_id: int,
    payload: HtmlSummaryGenerateRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> HtmlSummaryResponse:
    meeting = _get_owned_meeting(repo, meeting_id, current_user.id)
    transcript = " ".join(item.text or "" for item in meeting.transcriptions)
    data = {
        "meeting_id": meeting.id,
        "title": meeting.title,
        "date": meeting.created_at.strftime("%Y-%m-%d %H:%M") if meeting.created_at else "",
        "minutes": meeting.minutes_text or "",
        "action_items": meeting.action_items_text or "",
        "resolutions": meeting.resolutions_text or "",
        "transcript": transcript,
    }
    chain = HtmlSummaryChain()
    html, error = chain.run(
        data,
        show_code=payload.show_code,
        show_flowchart=payload.show_flowchart,
    )
    if error and not html:
        raise HTTPException(status_code=400, detail=error)

    path = Path(chain.save(meeting_id, html))
    return HtmlSummaryResponse(
        meeting_id=meeting_id,
        html=html,
        file_name=path.name,
        updated_at=datetime.fromtimestamp(path.stat().st_mtime),
    )


@router.get("/{meeting_id}/terms", response_model=MeetingTermsResponse)
def get_meeting_terms(
    meeting_id: int,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> MeetingTermsResponse:
    _get_owned_meeting(repo, meeting_id, current_user.id)
    return MeetingTermsResponse(meeting_id=meeting_id, terms=load_terms(meeting_id))


@router.patch("/{meeting_id}/project", response_model=MeetingMutationResponse)
def update_meeting_project_name(
    meeting_id: int,
    payload: MeetingProjectUpdateRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> MeetingMutationResponse:
    success = repo.update_meeting_project_name(
        meeting_id,
        (payload.project_name or "").strip(),
        user_id=current_user.id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return MeetingMutationResponse(success=True)


@router.delete("/{meeting_id}", response_model=MeetingMutationResponse)
def delete_meeting(
    meeting_id: int,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> MeetingMutationResponse:
    html_summary_path = get_html_summary_path(meeting_id)
    success = repo.delete_meeting(meeting_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Meeting not found")

    try:
        get_retriever().remove_meeting(meeting_id)
    except Exception:
        pass
    try:
        if html_summary_path.exists():
            html_summary_path.unlink()
    except Exception:
        pass

    return MeetingMutationResponse(success=True)


@router.post("/{meeting_id}/regenerate", response_model=CreateJobResponse)
def regenerate_meeting(
    meeting_id: int,
    payload: MeetingRegenerateRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> CreateJobResponse:
    meeting = _get_owned_meeting(repo, meeting_id, current_user.id)
    if not meeting.audio_path:
        raise HTTPException(status_code=400, detail="Original audio file is missing")

    parsed_terms, _ = truncate_terms(payload.terms or [])
    save_terms(meeting_id, parsed_terms)
    job = job_manager.create_job("meeting_regenerate")

    def run_regenerate() -> dict[str, str | int | None]:
        fresh_repo = MeetingRepository()
        current = fresh_repo.get_meeting_by_id(meeting_id, user_id=current_user.id)
        if not current or not current.audio_path:
            raise RuntimeError("Original audio file is missing")

        service = MeetingService(fresh_repo)
        stage_map = [
            (0, "loaded"),
            (10, "transcribing"),
            (65, "generating_minutes"),
            (82, "saving"),
            (92, "indexing"),
            (100, "done"),
        ]

        def on_progress(pct: int, message: str) -> None:
            stage = "running"
            for threshold, name in stage_map:
                if pct >= threshold:
                    stage = name
            job_manager.update_job(
                job.job_id,
                progress_pct=pct,
                stage=stage,
                message=message,
            )

        on_progress(10, "重新转写原始音频")
        engine = service._get_engine("faster-whisper")
        segments, _ = engine.transcribe(current.audio_path, terms=parsed_terms or None)
        transcript = " ".join(seg.get("text", "") for seg in segments)

        on_progress(65, "生成新的会议纪要")
        date_str = current.created_at.strftime("%Y-%m-%d %H:%M") if current.created_at else ""
        chain = MinutesChain()
        # 纪要与摘要/项目名一并在同一次 LLM 调用中产出
        action_items, resolutions, minutes, short_summary, project_name = chain.run(
            transcript,
            title=current.title,
            date=date_str,
        )
        if not (action_items or "").strip():
            action_items = PLACEHOLDER_NO_ACTION
        if not (resolutions or "").strip():
            resolutions = PLACEHOLDER_NO_RESOLUTION
        if not (short_summary or "").strip():
            short_summary = (minutes or "")[:200]
        if not (project_name or "").strip():
            project_name = "未分类"

        on_progress(82, "保存新的会议结果")
        fresh_repo.replace_transcriptions(meeting_id, segments, user_id=current_user.id)
        fresh_repo.update_meeting_results(
            meeting_id,
            minutes,
            action_items,
            resolutions,
            short_summary=short_summary,
            project_name=project_name,
            user_id=current_user.id,
        )
        TodoService(fresh_repo).sync_meeting_todos(
            current_user.id,
            meeting_id,
            action_items,
            replace=True,
        )

        on_progress(92, "更新知识库索引")
        try:
            get_retriever().rebuild_meeting_index(
                meeting_id,
                transcript=transcript,
                minutes=minutes,
                action_items=action_items,
                resolutions=resolutions,
                segments=segments,
                asr_model="faster-whisper",
            )
        except Exception:
            pass

        return {
            "meeting_id": meeting_id,
            "title": current.title,
            "output_path": None,
        }

    job_manager.run_in_thread(job.job_id, run_regenerate)
    return CreateJobResponse(job_id=job.job_id, status=job.status)


@router.post("/process", response_model=CreateJobResponse)
async def process_meeting(
    file: UploadFile = File(...),
    title: str = Form(...),
    meeting_date: str = Form(...),
    meeting_time: str = Form(...),
    output_format: str = Form("docx"),
    scene: str = Form(PromptTemplateLoader.DEFAULT_SCENE),
    asr_model: str = Form(ASR_MODEL_SENSEVOICE),
    chunk_strategy: str = Form(config.CHUNK_STRATEGY_FIXED),
    transcription_mode: str = Form("auto"),
    terms: str | None = Form(None),
    template_name: str | None = Form(None),
    is_private: bool = Form(False),
    current_user=Depends(get_current_user),
) -> CreateJobResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing uploaded file")

    suffix = Path(file.filename).suffix.lower()
    if (
        suffix not in config.ALLOWED_AUDIO_EXTENSIONS
        and suffix not in config.ALLOWED_VIDEO_EXTENSIONS
    ):
        raise HTTPException(status_code=400, detail="Unsupported file type")

    try:
        meeting_dt = datetime.fromisoformat(f"{meeting_date}T{meeting_time}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid meeting date or time") from exc

    file_service = FileService()
    saved_path, file_hash, ext = _save_uploaded_file(file_service, file)
    prepared_audio_path = file_service.prepare_audio_path(saved_path, ext)
    parsed_terms = _parse_terms(terms)
    resolved_template_path = (
        get_template_path(template_name, output_format) if template_name else None
    )

    job = job_manager.create_job("meeting_process")

    def run_process() -> dict[str, str | int | None]:
        work_repo = MeetingRepository()
        service = MeetingService(work_repo)

        stage_map = [
            (0, "uploaded"),
            (10, "transcribing"),
            (55, "analyzing"),
            (65, "generating_minutes"),
            (72, "generating_summary"),
            (80, "saving"),
            (88, "indexing"),
            (95, "exporting"),
            (100, "done"),
        ]

        def on_progress(pct: int, message: str) -> None:
            stage = "running"
            for threshold, name in stage_map:
                if pct >= threshold:
                    stage = name
            job_manager.update_job(
                job.job_id,
                progress_pct=pct,
                stage=stage,
                message=message,
            )

        result = None
        for event in service.process_stream(
            prepared_audio_path,
            file_hash,
            title,
            meeting_dt,
            user_id=current_user.id,
            output_format=output_format,
            template_path=resolved_template_path,
            progress_callback=on_progress,
            scene=scene,
            custom_headings=None,
            asr_model=asr_model,
            terms=parsed_terms or None,
            chunk_strategy=chunk_strategy,
            transcription_mode=transcription_mode,
            is_private=is_private,
        ):
            if event["type"] == "complete":
                result = event["data"]

        if not result:
            raise RuntimeError("Meeting processing did not return a final result")

        TodoService(work_repo).sync_meeting_todos(
            current_user.id,
            int(result["meeting_id"]),
            str(result.get("action_items") or ""),
            replace=True,
        )

        return {
            "meeting_id": result.get("meeting_id"),
            "title": result.get("title"),
            "output_path": result.get("output_path"),
        }

    job_manager.run_in_thread(job.job_id, run_process)
    return CreateJobResponse(job_id=job.job_id, status=job.status)
