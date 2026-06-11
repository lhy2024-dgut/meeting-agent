import importlib
import sys
from types import ModuleType


def _load_main_with_stubs(monkeypatch):
    chat_agent = ModuleType("agents.chat_agent")
    chat_agent.ChatAgent = object
    db_repository = ModuleType("db.repository")
    db_repository.MeetingRepository = object
    asr_engine = ModuleType("engines.asr_engine")
    asr_engine.ASREngine = object
    meeting_service = ModuleType("services.meeting_service")
    meeting_service.MeetingService = object

    monkeypatch.setitem(sys.modules, "agents.chat_agent", chat_agent)
    monkeypatch.setitem(sys.modules, "db.repository", db_repository)
    monkeypatch.setitem(sys.modules, "engines.asr_engine", asr_engine)
    monkeypatch.setitem(sys.modules, "services.meeting_service", meeting_service)
    sys.modules.pop("main", None)
    return importlib.import_module("main")


def test_run_eval_respects_enable_reranker(monkeypatch):
    main = _load_main_with_stubs(monkeypatch)

    class FakeRetriever:
        def __init__(self):
            self.calls = []

        def search(self, query, **kwargs):
            self.calls.append((query, kwargs))
            return [{"text": "包含待办事项"}]

    retriever = FakeRetriever()
    eval_set = [{"query": "有哪些待办事项", "keywords": ["待办"]}]

    hit, total, failed = main._run_eval(
        retriever,
        eval_set,
        mode="hybrid",
        top_k=5,
        enable_reranker=True,
    )

    assert (hit, total, failed) == (1, 1, [])
    assert retriever.calls == [
        ("有哪些待办事项", {"top_k": 5, "mode": "hybrid", "enable_reranker": True})
    ]


def test_eval_hit_supports_all_match(monkeypatch):
    main = _load_main_with_stubs(monkeypatch)

    assert main._eval_hit("包含议题和讨论内容", {"keywords": ["议题", "讨论"], "match": "all"})
    assert not main._eval_hit("只包含议题", {"keywords": ["议题", "讨论"], "match": "all"})
