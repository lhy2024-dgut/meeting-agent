from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from time import monotonic

from agents.chat_agent import ChatAgent


@dataclass
class ChatSession:
    session_id: str
    user_id: int
    mode: str
    meeting_id: int | None
    agent: ChatAgent
    last_accessed_at: float


class ChatSessionManager:
    SESSION_TTL_SECONDS = 30 * 60
    MAX_SESSIONS = 500

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._lock = threading.Lock()

    def create_session(
        self,
        *,
        user_id: int,
        mode: str,
        meeting_id: int | None,
        meeting_ids: list[int] | None = None,
        transcript: str = "",
        minutes: str = "",
        action_items: str = "",
        resolutions: str = "",
    ) -> ChatSession:
        agent = ChatAgent()
        if mode == "cross":
            agent.set_meeting_context(cross_meeting=True, meeting_ids=meeting_ids or [])
        else:
            agent.set_meeting_context(
                transcript,
                minutes,
                action_items,
                resolutions,
                meeting_id=meeting_id,
            )

        now = monotonic()
        session = ChatSession(
            session_id=uuid.uuid4().hex,
            user_id=user_id,
            mode=mode,
            meeting_id=meeting_id,
            agent=agent,
            last_accessed_at=now,
        )
        with self._lock:
            self._purge_expired_sessions(now)
            while len(self._sessions) >= self.MAX_SESSIONS:
                oldest_session_id = min(
                    self._sessions,
                    key=lambda item: self._sessions[item].last_accessed_at,
                )
                self._sessions.pop(oldest_session_id, None)
            self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> ChatSession | None:
        with self._lock:
            now = monotonic()
            self._purge_expired_sessions(now)
            session = self._sessions.get(session_id)
            if session:
                session.last_accessed_at = now
            return session

    def _purge_expired_sessions(self, now: float) -> None:
        expired_ids = [
            session_id
            for session_id, session in self._sessions.items()
            if now - session.last_accessed_at >= self.SESSION_TTL_SECONDS
        ]
        for session_id in expired_ids:
            self._sessions.pop(session_id, None)


chat_session_manager = ChatSessionManager()
