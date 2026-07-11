from unittest.mock import Mock

from rag.retriever import Retriever


def test_search_bm25_passes_filters_to_scoped_bm25():
    retriever = Retriever.__new__(Retriever)
    retriever._build_filters = Mock(
        return_value=(
            ["meeting_id = :meeting_id"],
            {"meeting_id": 42},
            {"meeting_id": 42},
        )
    )
    retriever._bm25_search = Mock(return_value=[{"meeting_id": 42, "chunk_type": "minutes", "score": 0.9}])
    retriever._hybrid_search = Mock()
    retriever._vector_search = Mock()
    retriever._get_reranker = Mock()

    results = retriever.search(
        "roadmap",
        top_k=3,
        meeting_id=42,
        mode="bm25",
        enable_reranker=False,
    )

    assert results == [{"meeting_id": 42, "chunk_type": "minutes", "score": 0.9}]
    retriever._bm25_search.assert_called_once_with(
        "roadmap",
        top_k=3,
        bm25_filters={"meeting_id": 42},
    )
    retriever._hybrid_search.assert_not_called()
    retriever._vector_search.assert_not_called()


def test_search_empty_meeting_ids_returns_empty():
    retriever = Retriever.__new__(Retriever)
    retriever._build_filters = Mock()
    retriever._bm25_search = Mock()
    retriever._hybrid_search = Mock()
    retriever._vector_search = Mock()

    results = retriever.search("roadmap", meeting_ids=[], mode="hybrid", enable_reranker=False)

    assert results == []
    retriever._build_filters.assert_not_called()
    retriever._bm25_search.assert_not_called()
    retriever._hybrid_search.assert_not_called()
    retriever._vector_search.assert_not_called()


def test_build_filters_returns_sql_and_bm25_filters():
    retriever = Retriever.__new__(Retriever)

    conditions, params, bm25_filters = retriever._build_filters(
        meeting_ids=[1, 2],
        exclude_meeting_id=3,
        chunk_type="minutes",
    )

    assert conditions == [
        "meeting_id IN :meeting_ids",
        "meeting_id != :exclude_id",
        "chunk_type = :ctype",
    ]
    assert params == {
        "meeting_ids": [1, 2],
        "exclude_id": 3,
        "ctype": "minutes",
    }
    assert bm25_filters == {
        "meeting_ids": [1, 2],
        "exclude_meeting_id": 3,
        "chunk_type": "minutes",
    }



def test_get_meeting_info_uses_expanding_in_clause():
    retriever = Retriever.__new__(Retriever)
    from unittest.mock import MagicMock

    retriever.engine = MagicMock()
    conn = retriever.engine.connect.return_value.__enter__.return_value
    conn.execute.return_value.fetchall.return_value = [
        (1, "Budget Review", "summary"),
        (2, "Roadmap", "summary2"),
    ]

    info = retriever._get_meeting_info([1, 2])

    assert info == {
        1: {"title": "Budget Review", "short_summary": "summary"},
        2: {"title": "Roadmap", "short_summary": "summary2"},
    }
    sql = conn.execute.call_args.args[0]
    params = conn.execute.call_args.args[1]
    rendered = str(sql)
    assert "WHERE id IN" in rendered
    assert "POSTCOMPILE_ids" in rendered
    assert params == {"ids": [1, 2]}
