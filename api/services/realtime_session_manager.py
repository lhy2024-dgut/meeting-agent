from __future__ import annotations

import hashlib
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import wave

import numpy as np

import config
from db.repository import MeetingRepository
from engines.asr_engine import _get_audio_duration
from engines.audio_utils import concat_wav_files, convert_audio_to_wav
from logger import get_logger
from services.meeting_service import MeetingService
from services.realtime_asr_service import get_realtime_service
from services.realtime_speaker_service import speaker_service
from services.terms_service import truncate_terms

logger = get_logger(__name__)


def _read_wav_pcm(wav_path: str) -> np.ndarray:
    """读取 16kHz 单声道 WAV 为 float32 PCM（范围 [-1, 1]）。"""
    with wave.open(str(wav_path), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
    if not frames:
        return np.array([], dtype=np.float32)
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


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
    stream_state: dict | None = None  # FunASR 流式 cache + 零头缓冲（跨分片共享）
    stream_finalized: bool = False
    audio_path: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    lock: threading.Lock = field(default_factory=threading.Lock)
    # 串行化分片处理，保护流式 cache（按到达顺序 = 录音顺序逐片处理）
    process_lock: threading.Lock = field(default_factory=threading.Lock)


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

        # 后台预加载 FunASR 流式模型 + 标点模型：
        # - 流式模型（约 12s）：避免第一个分片到达时才加载、录音初期长时间无字。
        # - 标点模型（ct-punc）：避免停止录音时才首次加载，导致 stop 请求超时。
        def _preload():
            asr = get_realtime_service()
            try:
                asr.ensure_streaming_ready()
            except Exception as exc:
                logger.warning("流式模型预加载失败（首个分片将重试）: %s", exc)
            try:
                asr.ensure_punctuation_ready()
            except Exception as exc:
                logger.warning("标点模型预加载失败（停止时将重试）: %s", exc)

        threading.Thread(target=_preload, daemon=True, name="rt-asr-preload").start()
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
        # process_lock 串行化每个会话的分片处理：无论请求以何种顺序/并发到达，
        # 都按拿到锁的先后（即到达顺序 = 前端串行上传的录音顺序）逐片喂给流式模型，
        # 保护共享 cache。不再用严格的 chunk_index==chunk_count 校验（那太脆弱：
        # 任一分片超时/失败就会导致后续全部 order mismatch 级联失败）。
        with session.process_lock:
            with session.lock:
                if session.status != "recording":
                    raise RuntimeError("Realtime session is not accepting chunks")
                if chunk_index in session.accepted_chunk_indices:
                    return session  # 幂等：重复上传的分片直接返回，避免重复计入

            chunk_path = self._session_dir(session) / f"chunk_{chunk_index:04d}{suffix}"
            wav_path = self._session_dir(session) / f"chunk_{chunk_index:04d}.wav"
            chunk_text = ""
            chunk_duration = 0.0
            wav_ok = False
            try:
                chunk_path.write_bytes(chunk_bytes)
                convert_audio_to_wav(chunk_path, wav_path)
                wav_ok = True
                chunk_duration = _get_audio_duration(str(wav_path))
                # FunASR paraformer-zh-streaming 流式转写：跨分片共享同一 cache
                asr = get_realtime_service()
                if session.stream_state is None:
                    session.stream_state = asr.create_stream_state()
                pcm = _read_wav_pcm(str(wav_path))
                chunk_text = asr.feed_stream_pcm(session.stream_state, pcm)
            except Exception as exc:
                # 单个分片解码/转写失败：跳过但仍计入，避免整段会话卡死
                logger.warning("实时分片 %d 处理失败，跳过: %s", chunk_index, exc)
                if chunk_duration <= 0:
                    chunk_duration = _get_audio_duration(str(chunk_path)) or 0.0

            with session.lock:
                session.chunk_count += 1
                session.duration_seconds = round(session.duration_seconds + chunk_duration, 2)
                session.chunk_paths.append(str(chunk_path))
                if wav_ok:
                    session.wav_paths.append(str(wav_path))
                session.accepted_chunk_indices.add(chunk_index)
                # week5 方式：直接把新识别文字拼接到持续增长的 transcript（无分段、无时间戳）。
                # 录音过程中标点较少，停止后再统一补标点。
                if chunk_text.strip():
                    session.transcript = (session.transcript + chunk_text).strip()
                session.updated_at = datetime.now()
                session.message = "transcribing"
        return session

    def stop_session(self, session_id: str) -> RealtimeSessionState:
        session = self._require_session(session_id)
        # 先刷出流式尾音并对整段文字补标点（幂等，只做一次）
        self._finalize_stream(session)
        with session.lock:
            # 不要把正在生成的会话降级为 stopped（否则会重开被 DELETE 误删的窗口）
            keep_status = session.status == "generating"

            def _set_stopped(msg: str) -> None:
                if not keep_status:
                    session.status = "stopped"
                    session.message = msg
                session.updated_at = datetime.now()

            if session.audio_path:
                _set_stopped("recording stopped")
                return session

            if not session.wav_paths:
                _set_stopped("no audio chunks received")
                return session

            output_path = self._session_dir(session) / "recording.wav"
            session.audio_path = concat_wav_files(session.wav_paths, output_path)
            _set_stopped("recording stopped")
        return session

    def _finalize_stream(self, session: RealtimeSessionState) -> None:
        """刷出流式模型尾音并对完整文本做一次性标点恢复（幂等）。

        停止录音时调用：把最后的尾音刷出、对整段连续文本补标点，并构造单条
        segment 供后续生成会议纪要使用（实时转写不保留时间戳粒度）。
        """
        # 先拿 process_lock，确保最后一个分片已处理完再刷尾音，避免与分片处理并发喂 cache
        with session.process_lock:
            with session.lock:
                if session.stream_finalized:
                    return
                session.stream_finalized = True
                state = session.stream_state
            if state is None:
                return
            try:
                asr = get_realtime_service()
                tail = asr.finalize_stream(state)
                with session.lock:
                    if tail.strip():
                        session.transcript = (session.transcript + tail).strip()
                    raw_text = session.transcript
                punctuated = asr.apply_punctuation_text(raw_text)
                with session.lock:
                    session.transcript = (punctuated or raw_text).strip()
                    if session.transcript:
                        session.segments = [
                            {
                                "start": 0.0,
                                "end": session.duration_seconds,
                                "timestamp": 0.0,
                                "text": session.transcript,
                                "audio_segment": "",
                            }
                        ]
            except Exception as exc:
                logger.warning("流式尾音/标点处理失败: %s", exc)

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
                    # 说话人标签由前端单独展示在上方，正文不再重复前缀 [说话人X]
                    "text": (item.get("text", "") or "").strip(),
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

    def generate_meeting(self, session_id: str) -> dict[str, object]:
        # 尽早标记 generating：cleanup_session(force=False) 遇到 generating 会拒绝删除，
        # 防止前端卸载/轮询触发的 DELETE 在生成期间删掉会话目录（含 recording.wav）。
        session = self._require_session(session_id)
        with session.lock:
            session.status = "generating"
            session.message = "generating meeting"
            session.updated_at = datetime.now()

        session = self.stop_session(session_id)
        if not session.audio_path:
            raise RuntimeError("No recording available to generate a meeting")

        service = MeetingService(MeetingRepository())
        source_segments = session.speaker_segments or session.segments
        if not source_segments:
            raise RuntimeError("No transcript segments available to generate a meeting")

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
