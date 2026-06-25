from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass

from agents.chat_agent import ChatAgent


@dataclass
class ChatSession:
    session_id: str
    mode: str
    meeting_id: int | None
    agent: ChatAgent


class ChatSessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._lock = threading.Lock()

    def create_session(
        self,
        *,
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

        session = ChatSession(
            session_id=uuid.uuid4().hex,
            mode=mode,
            meeting_id=meeting_id,
            agent=agent,
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> ChatSession | None:
        with self._lock:
            return self._sessions.get(session_id)


chat_session_manager = ChatSessionManager()
