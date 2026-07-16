from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from api.deps import get_current_user
from api.schemas.jobs import CreateJobResponse
from api.schemas.realtime import (
    RealtimeSessionCreateRequest,
    RealtimeSessionMutationResponse,
    RealtimeSessionResponse,
)
from api.services.job_manager import job_manager
from api.services.realtime_session_manager import normalize_terms, realtime_session_manager

router = APIRouter(prefix="/api/realtime", tags=["realtime"])


def _get_owned_session(session_id: str, user_id: int):
    session = realtime_session_manager.get_session(session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Realtime session not found")
    return session


@router.post("/sessions", response_model=RealtimeSessionResponse)
def create_realtime_session(
    payload: RealtimeSessionCreateRequest,
    current_user=Depends(get_current_user),
) -> RealtimeSessionResponse:
    session = realtime_session_manager.create_session(
        user_id=current_user.id,
        title=payload.title,
        meeting_date=payload.meeting_date,
        meeting_time=payload.meeting_time,
        output_format=payload.output_format,
        scene=payload.scene,
        asr_model=payload.asr_model,
        terms=normalize_terms(payload.terms),
    )
    return RealtimeSessionResponse(**realtime_session_manager.serialize(session))


@router.get("/sessions/{session_id}", response_model=RealtimeSessionResponse)
def get_realtime_session(
    session_id: str,
    current_user=Depends(get_current_user),
) -> RealtimeSessionResponse:
    session = _get_owned_session(session_id, current_user.id)
    return RealtimeSessionResponse(**realtime_session_manager.serialize(session))


@router.post("/sessions/{session_id}/chunks", response_model=RealtimeSessionResponse)
async def append_realtime_chunk(
    session_id: str,
    file: UploadFile = File(...),
    chunk_index: int = Form(...),
    current_user=Depends(get_current_user),
) -> RealtimeSessionResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing chunk file")

    _get_owned_session(session_id, current_user.id)
    try:
        suffix = Path(file.filename).suffix.lower() or ".webm"
        payload = await file.read()
        # 分片转写含 ffmpeg + FunASR 推理（阻塞、耗时），放进线程池执行，
        # 避免阻塞事件循环导致其它请求（如待办更新）全部超时。
        session = await run_in_threadpool(
            realtime_session_manager.append_chunk,
            session_id,
            payload,
            suffix,
            chunk_index,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Realtime session not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RealtimeSessionResponse(**realtime_session_manager.serialize(session))


@router.post("/sessions/{session_id}/stop", response_model=RealtimeSessionResponse)
def stop_realtime_session(
    session_id: str,
    current_user=Depends(get_current_user),
) -> RealtimeSessionResponse:
    _get_owned_session(session_id, current_user.id)
    try:
        session = realtime_session_manager.stop_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Realtime session not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RealtimeSessionResponse(**realtime_session_manager.serialize(session))


@router.post("/sessions/{session_id}/diarize", response_model=RealtimeSessionResponse)
def diarize_realtime_session(
    session_id: str,
    current_user=Depends(get_current_user),
) -> RealtimeSessionResponse:
    _get_owned_session(session_id, current_user.id)
    try:
        session = realtime_session_manager.diarize_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Realtime session not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RealtimeSessionResponse(**realtime_session_manager.serialize(session))


@router.post("/sessions/{session_id}/generate", response_model=CreateJobResponse)
def generate_realtime_meeting(
    session_id: str,
    current_user=Depends(get_current_user),
) -> CreateJobResponse:
    _get_owned_session(session_id, current_user.id)
    job = job_manager.create_job("realtime_meeting_process")

    def run_generate():
        return realtime_session_manager.generate_meeting(session_id)

    job_manager.run_in_thread(job.job_id, run_generate)
    return CreateJobResponse(job_id=job.job_id, status=job.status)


@router.delete("/sessions/{session_id}", response_model=RealtimeSessionMutationResponse)
def delete_realtime_session(
    session_id: str,
    current_user=Depends(get_current_user),
) -> RealtimeSessionMutationResponse:
    session = realtime_session_manager.get_session(session_id)
    if not session:
        return RealtimeSessionMutationResponse(success=True)
    if session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Realtime session not found")

    cleaned = realtime_session_manager.cleanup_session(session_id)
    if not cleaned:
        raise HTTPException(status_code=409, detail="Realtime session is still generating")
    return RealtimeSessionMutationResponse(success=True)
