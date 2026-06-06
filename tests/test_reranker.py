from rag.reranker import Reranker


class _FakeTokenizer:
    def __call__(self, pairs, **kwargs):
        return {"pairs": pairs}


class _FakeScores:
    def __init__(self, values):
        self._values = values

    def squeeze(self, dim):
        return self

    def dim(self):
        return 1

    def tolist(self):
        return list(self._values)


class _FakeModelResult:
    def __init__(self, values):
        self.logits = _FakeScores(values)


class _FakeModel:
    def __call__(self, **inputs):
        return _FakeModelResult([0.2, 0.9])


class _NoGrad:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeTorch:
    @staticmethod
    def no_grad():
        return _NoGrad()


def test_rerank_does_not_mutate_input_results():
    reranker = Reranker.__new__(Reranker)
    reranker.tokenizer = _FakeTokenizer()
    reranker.model = _FakeModel()
    reranker._torch = _FakeTorch()

    original = [
        {"text": "doc-a", "score": 0.3},
        {"text": "doc-b", "score": 0.4},
    ]
    snapshot = [dict(item) for item in original]

    reranked = reranker.rerank("query", original, top_k=2)

    assert original == snapshot
    assert reranked[0]["text"] == "doc-b"
    assert reranked[0]["rerank_score"] == 0.9
    assert reranked[1]["text"] == "doc-a"
    assert reranked[1]["rerank_score"] == 0.2
