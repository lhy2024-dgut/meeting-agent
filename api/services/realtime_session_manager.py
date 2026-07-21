from __future__ import annotations

import hashlib
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import config
from db.repository import MeetingRepository
from engines.asr_engine import _get_audio_duration
from engines.audio_utils import concat_wav_files, convert_audio_to_wav
from services.meeting_service import MeetingService
from services.realtime_speaker_service import speaker_service
from services.terms_service import truncate_terms


@dataclass
class RealtimeSessionState:
    session_id: str
    user_id: int
    title: str
    meeting_date: str
    meeting_time: str
    output_format: str
    scene: str
    asr_model: str
    terms: list[str] = field(default_factory=list)
    status: str = "idle"
    message: str = "session created"
    transcript: str = ""
    duration_seconds: float = 0.0
    chunk_count: int = 0
    chunk_paths: list[str] = field(default_factory=list)
    wav_paths: list[str] = field(default_factory=list)
    segments: list[dict] = field(default_factory=list)
    speaker_segments: list[dict] = field(default_factory=list)
    accepted_chunk_indices: set[int] = field(default_factory=set)
    processing_chunk_indices: set[int] = field(default_factory=set)
    audio_path: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    lock: threading.Lock = field(default_factory=threading.Lock)


class RealtimeSessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, RealtimeSessionState] = {}
        self._lock = threading.Lock()
        self._storage_root = config.AUDIO_DIR / "realtime_sessions"
        self._storage_root.mkdir(parents=True, exist_ok=True)

    def create_session(
        self,
        *,
        user_id: int,
        title: str,
        meeting_date: str,
        meeting_time: str,
        output_format: str,
        scene: str,
        asr_model: str,
        terms: list[str],
    ) -> RealtimeSessionState:
        session = RealtimeSessionState(
            session_id=uuid.uuid4().hex,
            user_id=user_id,
            title=title.strip() or f"Realtime_{datetime.now().strftime('%Y%m%d_%H%M')}",
            meeting_date=meeting_date,
            meeting_time=meeting_time,
            output_format=output_format,
            scene=scene,
            asr_model=asr_model,
            terms=terms,
            status="recording",
            message="recording",
        )
        with self._lock:
            self._sessions[session.session_id] = session
        self._session_dir(session).mkdir(parents=True, exist_ok=True)
        return session

    def get_session(self, session_id: str) -> RealtimeSessionState | None:
        with self._lock:
            return self._sessions.get(session_id)

    def append_chunk(
        self,
        session_id: str,
        chunk_bytes: bytes,
        suffix: str,
        chunk_index: int,
    ) -> RealtimeSessionState:
        session = self._require_session(session_id)
        with session.lock:
            if session.status != "recording":
                raise RuntimeError("Realtime session is not accepting chunks")
            if chunk_index in session.accepted_chunk_indices:
                return session
            if chunk_index in session.processing_chunk_indices:
                raise RuntimeError("Chunk is already being processed")
            if chunk_index != session.chunk_count:
                raise RuntimeError(
                    f"Chunk order mismatch: expected={session.chunk_count}, got={chunk_index}"
                )
            session.processing_chunk_indices.add(chunk_index)

        chunk_path = self._session_dir(session) / f"chunk_{chunk_index:04d}{suffix}"
        wav_path = self._session_dir(session) / f"chunk_{chunk_index:04d}.wav"
        try:
            chunk_path.write_bytes(chunk_bytes)
            convert_audio_to_wav(chunk_path, wav_path)

            service = MeetingService(MeetingRepository())
            engine = service._get_engine(session.asr_model)
            chunk_duration = _get_audio_duration(str(wav_path))
            chunk_segments, _ = engine.transcribe(str(wav_path), terms=session.terms or None)

            with session.lock:
                if session.status != "recording":
                    session.processing_chunk_indices.discard(chunk_index)
                    raise RuntimeError("Realtime session stopped while chunk was processing")
                offset = session.duration_seconds
                for item in chunk_segments:
                    session.segments.append(
                        {
                            "start": round((item.get("start") or 0.0) + offset, 2),
                            "end": round((item.get("end") or 0.0) + offset, 2),
                            "timestamp": round((item.get("start") or 0.0) + offset, 2),
                            "text": item.get("text", ""),
                            "audio_segment": str(wav_path),
                        }
                    )
                session.chunk_count += 1
                session.duration_seconds = round(offset + chunk_duration, 2)
                session.chunk_paths.append(str(chunk_path))
                session.wav_paths.append(str(wav_path))
                session.accepted_chunk_indices.add(chunk_index)
                session.transcript = " ".join(seg.get("text", "") for seg in session.segments).strip()
                session.updated_at = datetime.now()
                session.message = "transcribing"
                session.processing_chunk_indices.discard(chunk_index)
            return session
        except Exception:
            with session.lock:
                session.processing_chunk_indices.discard(chunk_index)
            raise

    def stop_session(self, session_id: str) -> RealtimeSessionState:
        session = self._require_session(session_id)
        with session.lock:
            if session.audio_path:
                session.status = "stopped"
                session.message = "recording stopped"
                session.updated_at = datetime.now()
                return session

            if not session.wav_paths:
                session.status = "stopped"
                session.message = "no audio chunks received"
                session.updated_at = datetime.now()
                return session

            output_path = self._session_dir(session) / "recording.wav"
            session.audio_path = concat_wav_files(session.wav_paths, output_path)
            session.status = "stopped"
            session.message = "recording stopped"
            session.updated_at = datetime.now()
        return session

    def diarize_session(self, session_id: str) -> RealtimeSessionState:
        session = self.stop_session(session_id)
        if not session.audio_path:
            raise RuntimeError("No recording available for speaker diarization")

        speaker_segments = speaker_service.diarize(session.audio_path)
        with session.lock:
            session.status = "diarized"
            session.speaker_segments = [
                {
                    "start": item.get("start", 0.0),
                    "end": item.get("end", 0.0),
                    "timestamp": item.get("start", 0.0),
                    "text": f"[{item.get('spk', 'Speaker')}] {item.get('text', '')}".strip(),
                    "speaker": item.get("spk", "Speaker"),
                }
                for item in speaker_segments
            ]
            session.updated_at = datetime.now()
            session.message = (
                "speaker diarization completed"
                if session.speaker_segments
                else "speaker diarization returned no labels"
            )
        return session

    def generate_meeting(self, session_id: str, is_private: bool = False) -> dict[str, object]:
        session = self.stop_session(session_id)
        if not session.audio_path:
            raise RuntimeError("No recording available to generate a meeting")

        service = MeetingService(MeetingRepository())
        source_segments = session.speaker_segments or session.segments
        if not source_segments:
            raise RuntimeError("No transcript segments available to generate a meeting")

        with session.lock:
            session.status = "generating"
            session.message = "generating meeting"
            session.updated_at = datetime.now()

        try:
            meeting_dt = datetime.fromisoformat(f"{session.meeting_date}T{session.meeting_time}")
            file_hash = hashlib.sha256(Path(session.audio_path).read_bytes()).hexdigest()
            return service.process_from_realtime(
                segments=source_segments,
                audio_path=session.audio_path,
                file_hash=file_hash,
                title=session.title,
                meeting_dt=meeting_dt,
                user_id=session.user_id,
                output_format=session.output_format,
                scene=session.scene,
                terms=session.terms or None,
                is_private=is_private,
            )
        finally:
            self.cleanup_session(session_id, force=True)

    def serialize(self, session: RealtimeSessionState) -> dict[str, object]:
        with session.lock:
            return {
                "session_id": session.session_id,
                "title": session.title,
                "meeting_date": session.meeting_date,
                "meeting_time": session.meeting_time,
                "output_format": session.output_format,
                "scene": session.scene,
                "asr_model": session.asr_model,
                "terms": session.terms,
                "status": session.status,
                "message": session.message,
                "transcript": session.transcript,
                "duration_seconds": session.duration_seconds,
                "chunk_count": session.chunk_count,
                "segments": list(session.segments),
                "speaker_segments": list(session.speaker_segments),
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            }

    def _require_session(self, session_id: str) -> RealtimeSessionState:
        session = self.get_session(session_id)
        if not session:
            raise KeyError(session_id)
        return session

    def _session_dir(self, session: RealtimeSessionState) -> Path:
        return self._storage_root / session.session_id

    def cleanup_session(self, session_id: str, force: bool = False) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
        if not session:
            return False

        with session.lock:
            if session.status == "generating" and not force:
                return False
            session.status = "cleaned"
            session.updated_at = datetime.now()

        with self._lock:
            self._sessions.pop(session_id, None)

        shutil.rmtree(self._session_dir(session), ignore_errors=True)
        return True


def normalize_terms(terms: list[str] | None) -> list[str]:
    kept, _ = truncate_terms(terms or [])
    return kept


realtime_session_manager = RealtimeSessionManager()
