from unittest.mock import Mock

from rag.bm25_index import BM25Index


def test_search_reuses_cached_bm25_for_full_corpus():
    index = BM25Index()
    index._docs = {
        1: {"meeting_id": 1, "chunk_type": "minutes", "chunk_index": 0, "text": "alpha", "tokens": ["alpha"]},
        2: {"meeting_id": 2, "chunk_type": "minutes", "chunk_index": 0, "text": "beta", "tokens": ["beta"]},
    }
    cached_bm25 = Mock()
    cached_bm25.get_scores.return_value = [2.0, 1.0]
    index._get_bm25 = Mock(return_value=(cached_bm25, [1, 2]))

    results = index.search("alpha", top_k=2)

    index._get_bm25.assert_called_once_with()
    assert results[0]["meeting_id"] == 1
    assert results[1]["meeting_id"] == 2
