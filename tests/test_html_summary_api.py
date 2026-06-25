from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_current_user, get_meeting_repository
from api.routers import meetings


class _FakeRetriever:
    def remove_meeting(self, _meeting_id):
        return None


class _FakeHtmlSummaryChain:
    def run(self, data, show_code=False, show_flowchart=True):
        html = (
            "<div class='header'><div class='header-title'>"
            f"{data['title']}"
            "</div></div><div class='summary'>测试可视化纪要</div>"
        )
        return html, ""

    def save(self, meeting_id, html):
        path = _fake_summary_path(meeting_id)
        path.write_text(html, encoding="utf-8")
        return str(path)


def _fake_summary_path(meeting_id: int) -> Path:
    raise RuntimeError("summary path not configured")


def test_html_summary_generate_get_and_delete_cleanup(tmp_path, monkeypatch):
    app = FastAPI()
    app.include_router(meetings.router)

    meeting = SimpleNamespace(
        id=1,
        title="HTML Summary Test",
        created_at=datetime(2026, 6, 25, 11, 0),
        updated_at=datetime(2026, 6, 25, 11, 0),
        minutes_text="## 结论\n- 需要同步推进",
        action_items_text="- 完成 PR",
        resolutions_text="- 同意上线",
        transcriptions=[
            SimpleNamespace(
                id=1,
                text="会议原文",
                timestamp=0.0,
                start_time=0.0,
                end_time=1.0,
            )
        ],
    )

    class FakeRepo:
        def __init__(self):
            self.deleted = False

        def get_meeting_by_id(self, meeting_id, user_id=None):
            return None if self.deleted or meeting_id != 1 else meeting

        def delete_meeting(self, meeting_id, user_id=None):
            if meeting_id != 1 or self.deleted:
                return False
            self.deleted = True
            return True

    repo = FakeRepo()
    app.dependency_overrides[get_meeting_repository] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, username="tester")

    summary_path = tmp_path / "meeting_1_summary.html"

    def fake_summary_path(meeting_id: int) -> Path:
        return tmp_path / f"meeting_{meeting_id}_summary.html"

    monkeypatch.setattr("api.routers.meetings.HtmlSummaryChain", _FakeHtmlSummaryChain)
    monkeypatch.setattr("api.routers.meetings.get_html_summary_path", fake_summary_path)
    monkeypatch.setattr("api.routers.meetings.get_retriever", lambda: _FakeRetriever())
    monkeypatch.setattr(__name__ + "._fake_summary_path", fake_summary_path)

    client = TestClient(app)

    generated = client.post(
        "/api/meetings/1/html-summary/generate",
        json={"show_code": False, "show_flowchart": True},
    )
    assert generated.status_code == 200
    assert generated.json()["meeting_id"] == 1
    assert summary_path.exists()

    fetched = client.get("/api/meetings/1/html-summary")
    assert fetched.status_code == 200
    assert "测试可视化纪要" in fetched.json()["html"]

    deleted = client.delete("/api/meetings/1")
    assert deleted.status_code == 200
    assert deleted.json()["success"] is True
    assert not summary_path.exists()
