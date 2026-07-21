from pathlib import Path
from types import SimpleNamespace
import wave

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_current_user
from api.routers import realtime
from api.services.realtime_session_manager import realtime_session_manager


def _write_wav(path: Path, duration_seconds: float = 1.0) -> None:
    sample_rate = 16000
    frame_count = int(sample_rate * duration_seconds)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frame_count)


def test_realtime_session_chunk_dedup_and_cleanup(tmp_path, monkeypatch):
    app = FastAPI()
    app.include_router(realtime.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, username="tester")
    client = TestClient(app)

    realtime_session_manager._sessions.clear()
    realtime_session_manager._storage_root = tmp_path / "realtime_sessions"
    realtime_session_manager._storage_root.mkdir(parents=True, exist_ok=True)

    def fake_convert_audio_to_wav(_input_path, output_path=None, sample_rate=16000):
        out = Path(output_path)
        _write_wav(out, duration_seconds=1.25)
        return str(out)

    class FakeRealtimeService:
        def ensure_streaming_ready(self):
            return None

        def ensure_punctuation_ready(self):
            return None

        def create_stream_state(self):
            return {}

        def feed_stream_pcm(self, _state, _pcm):
            return "测试分片"

        def finalize_stream(self, _state):
            return ""

        def apply_punctuation_text(self, text):
            return text

    monkeypatch.setattr(
        "api.services.realtime_session_manager.convert_audio_to_wav",
        fake_convert_audio_to_wav,
    )
    monkeypatch.setattr(
        "api.services.realtime_session_manager._get_audio_duration",
        lambda _path: 1.25,
    )
    monkeypatch.setattr(
        "api.services.realtime_session_manager.get_realtime_service",
        lambda: FakeRealtimeService(),
    )

    created = client.post(
        "/api/realtime/sessions",
        json={
            "title": "Realtime Test",
            "meeting_date": "2026-06-25",
            "meeting_time": "10:30",
            "output_format": "md",
            "scene": "通用会议",
            "asr_model": "faster-whisper",
            "terms": ["纪要"],
        },
    )
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    files = {"file": ("chunk_0.webm", b"fake-bytes", "audio/webm")}
    data = {"chunk_index": "0"}
    first_chunk = client.post(f"/api/realtime/sessions/{session_id}/chunks", files=files, data=data)
    assert first_chunk.status_code == 200
    first_payload = first_chunk.json()
    assert first_payload["chunk_count"] == 1
    assert first_payload["transcript"] == "测试分片"

    duplicate_chunk = client.post(f"/api/realtime/sessions/{session_id}/chunks", files=files, data=data)
    assert duplicate_chunk.status_code == 200
    duplicate_payload = duplicate_chunk.json()
    assert duplicate_payload["chunk_count"] == 1
    assert duplicate_payload["transcript"] == "测试分片"

    stopped = client.post(f"/api/realtime/sessions/{session_id}/stop")
    assert stopped.status_code == 200

    deleted = client.delete(f"/api/realtime/sessions/{session_id}")
    assert deleted.status_code == 200
    assert deleted.json()["success"] is True
    assert realtime_session_manager.get_session(session_id) is None
    assert not (tmp_path / "realtime_sessions" / session_id).exists()
