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

# 单个分片解码（ffmpeg 转 wav）失败的最大尝试次数；超过则跳过并显式记录，避免卡死后续
MAX_CHUNK_ATTEMPTS = 3


class RetryableChunkError(RuntimeError):
    """分片处理暂时性失败（尚未达重试上限）。接口应返回可重试状态，前端重传同一分片。"""


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
    is_private: bool = False
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
    # ── 重排序缓冲：按索引缓存已到达但尚未按序处理的分片，只连续处理下一个期望分片 ──
    pending_chunks: dict[int, str] = field(default_factory=dict)  # index -> 已落盘的原始分片路径
    next_index: int = 0                                            # 下一个要按序处理的分片索引
    chunk_attempts: dict[int, int] = field(default_factory=dict)  # index -> 已尝试处理次数
    dropped_chunk_indices: set[int] = field(default_factory=set)  # 达重试上限被跳过的硬失败分片
    transcription_failed_indices: set[int] = field(default_factory=set)  # wav 成功但转写失败（录音在、文字缺）
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
        is_private: bool = False,
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
            is_private=is_private,
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
        with session.lock:
            if session.status != "recording":
                raise RuntimeError("Realtime session is not accepting chunks")
            # 幂等：已成功接受、或已判定硬失败跳过的分片，直接返回，不重复处理
            if (
                chunk_index in session.accepted_chunk_indices
                or chunk_index in session.dropped_chunk_indices
            ):
                return session

        # 先把原始分片落盘（不占内存），登记到按索引的重排序缓冲区
        raw_path = self._session_dir(session) / f"chunk_{chunk_index:04d}{suffix}"
        raw_path.write_bytes(chunk_bytes)
        with session.lock:
            # 早已越过的迟到分片（index < next_index），无需再处理
            if chunk_index < session.next_index:
                return session
            session.pending_chunks[chunk_index] = str(raw_path)

        # 串行地按序处理尽可能多的连续分片，保证流式 cache 按录音顺序喂入
        with session.process_lock:
            self._drain_pending(session)

        # 若本分片正是当前期望分片、但解码暂时失败仍可重试，返回可重试错误让前端重传同一分片
        with session.lock:
            if (
                chunk_index not in session.accepted_chunk_indices
                and chunk_index not in session.dropped_chunk_indices
                and chunk_index == session.next_index
                and chunk_index in session.pending_chunks
            ):
                raise RetryableChunkError(
                    f"Chunk {chunk_index} temporarily failed to decode, please retry"
                )
        return session

    def _drain_pending(self, session: RealtimeSessionState) -> None:
        """在 process_lock 保护下，从 next_index 起连续按序处理已缓冲的分片。

        - 下一个期望分片尚未到达：停止（正常等待后续上传，解决乱序）。
        - ffmpeg 解码失败：累计尝试次数；未达上限则停止等待重传，达上限则跳过并显式记录
          （dropped_chunk_indices），避免坏分片永久卡死后续。
        - wav 有效但流式转写失败：仍接受该分片（录音不缺段），文字置空并记录
          （transcription_failed_indices），不静默丢失。
        """
        while True:
            with session.lock:
                idx = session.next_index
                raw_path = session.pending_chunks.get(idx)
            if raw_path is None:
                return  # 下一个期望分片还没到，正常等待

            try:
                wav_path, duration, text, transcribe_failed = self._transcribe_chunk(
                    session, idx, raw_path
                )
            except Exception as exc:
                with session.lock:
                    session.chunk_attempts[idx] = session.chunk_attempts.get(idx, 0) + 1
                    attempts = session.chunk_attempts[idx]
                if attempts < MAX_CHUNK_ATTEMPTS:
                    logger.warning(
                        "实时分片 %d 解码失败（第 %d/%d 次），等待前端重传: %s",
                        idx, attempts, MAX_CHUNK_ATTEMPTS, exc,
                    )
                    return  # 保留 pending，next_index 不推进，等前端重传同一分片
                # 达上限：硬失败，显式记录并跳过，避免坏分片永久卡死后续分片
                logger.error(
                    "实时分片 %d 连续解码失败 %d 次，跳过该段音频: %s", idx, attempts, exc
                )
                with session.lock:
                    session.dropped_chunk_indices.add(idx)
                    session.pending_chunks.pop(idx, None)
                    session.next_index += 1
                    session.updated_at = datetime.now()
                    session.message = f"分片 {idx} 解码失败已跳过（录音缺失该段）"
                continue

            with session.lock:
                session.duration_seconds = round(session.duration_seconds + duration, 2)
                session.chunk_paths.append(raw_path)
                session.wav_paths.append(wav_path)
                session.accepted_chunk_indices.add(idx)
                session.chunk_count += 1
                # week5 方式：直接把新识别文字拼接到持续增长的 transcript（无分段、无时间戳）
                if text.strip():
                    session.transcript = (session.transcript + text).strip()
                if transcribe_failed:
                    session.transcription_failed_indices.add(idx)
                session.pending_chunks.pop(idx, None)
                session.next_index += 1
                session.updated_at = datetime.now()
                session.message = "transcribing"

    def _transcribe_chunk(
        self, session: RealtimeSessionState, idx: int, raw_path: str
    ) -> tuple[str, float, str, bool]:
        """处理单个分片：ffmpeg 转 wav + 流式转写。

        返回 (wav_path, duration, text, transcribe_failed)。
        ffmpeg 转 wav 失败会抛异常（由 _drain_pending 按重试策略处理）；
        流式转写失败不抛异常——wav 已生成、录音不缺段，仅该段文字缺失。
        仅在 process_lock 内被调用，故对共享 stream_state 的访问天然串行、无需额外加锁。
        """
        wav_path = self._session_dir(session) / f"chunk_{idx:04d}.wav"
        convert_audio_to_wav(raw_path, wav_path)  # 失败则抛 → 上层重试/跳过
        duration = _get_audio_duration(str(wav_path))

        text = ""
        transcribe_failed = False
        try:
            asr = get_realtime_service()
            if session.stream_state is None:
                session.stream_state = asr.create_stream_state()
            pcm = _read_wav_pcm(str(wav_path))
            text = asr.feed_stream_pcm(session.stream_state, pcm)
        except Exception as exc:
            transcribe_failed = True
            logger.error("实时分片 %d 转写失败（音频保留，文字缺失）: %s", idx, exc)
        return str(wav_path), duration, text, transcribe_failed

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
                state = session.stream_state
            # 把缓冲区里剩余的连续分片补处理完（延迟到达/最后一片）
            self._drain_pending(session)
            if state is None:
                with session.lock:
                    session.stream_finalized = True
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
                    # 成功后才置位，避免临时模型异常导致尾音/标点永久丢失且无法重试
                    session.stream_finalized = True
            except Exception as exc:
                logger.warning("流式尾音/标点处理失败，保留可重试状态: %s", exc)

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
                is_private=session.is_private,
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
                "is_private": session.is_private,
                "status": session.status,
                "message": session.message,
                "transcript": session.transcript,
                "duration_seconds": session.duration_seconds,
                "chunk_count": session.chunk_count,
                # 显式暴露失败分片，避免静默丢段（前端可提示用户）
                "dropped_chunk_count": len(session.dropped_chunk_indices),
                "transcription_failed_count": len(session.transcription_failed_indices),
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
