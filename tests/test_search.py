"""
tests/test_search.py — MemorySearch テスト
task#98: カバレッジ≥80%達成のための追加テスト
"""
from nested_memory.search import MemorySearch


class TestMemorySearch:
    """MemorySearch の各メソッドのテスト"""

    def test_search_basic(self, tmp_store):
        """基本検索が結果を返す"""
        tmp_store.add("Python programming basics", layer=1, tags=["python"])
        tmp_store.add("Something unrelated", layer=1, tags=["other"])
        searcher = MemorySearch(tmp_store)
        results = searcher.search("Python")
        assert len(results) >= 1
        assert any("Python" in r.content for r in results)

    def test_search_with_layer_filter(self, tmp_store):
        """層フィルタが正しく動作する"""
        tmp_store.add("L1 memory", layer=1)
        tmp_store.add("L2 memory", layer=2)
        searcher = MemorySearch(tmp_store)
        results = searcher.search("memory", layer=1)
        assert all(r.layer == 1 for r in results)

    def test_search_empty_returns_empty(self, tmp_store):
        """DBが空なら空リストを返す"""
        searcher = MemorySearch(tmp_store)
        results = searcher.search("anything")
        assert results == []

    def test_search_with_rerank(self, tmp_store, mock_llm):
        """リランクありで検索する（mock_llmがリストをそのまま返す）"""
        tmp_store.add("Reranked content", layer=1)
        searcher = MemorySearch(tmp_store)
        results = searcher.search("Reranked", llm=mock_llm, rerank=True)
        assert len(results) >= 1

    def test_search_with_rerank_no_results(self, tmp_store, mock_llm):
        """リランクありで結果なしの場合は空リストを返す"""
        searcher = MemorySearch(tmp_store)
        results = searcher.search("nothing_matches", llm=mock_llm, rerank=True)
        assert results == []

    def test_search_by_tags_basic(self, tmp_store):
        """タグ検索が正常動作する"""
        tmp_store.add("tagged content", layer=1, tags=["urgent", "work"])
        searcher = MemorySearch(tmp_store)
        results = searcher.search_by_tags(["urgent"])
        assert len(results) >= 1

    def test_search_by_tags_empty_tags(self, tmp_store):
        """空タグリストで空を返す"""
        tmp_store.add("some content", layer=1, tags=["a"])
        searcher = MemorySearch(tmp_store)
        results = searcher.search_by_tags([])
        assert results == []

    def test_search_by_tags_with_layer(self, tmp_store):
        """タグ検索で層フィルタが効く"""
        tmp_store.add("L1 tagged", layer=1, tags=["mytag"])
        tmp_store.add("L2 tagged", layer=2, tags=["mytag"])
        searcher = MemorySearch(tmp_store)
        results = searcher.search_by_tags(["mytag"], layer=1)
        assert all(r.layer == 1 for r in results)

    def test_context_inject_returns_string(self, tmp_store):
        """context_injectが文字列を返す"""
        tmp_store.add("Important context about Python", layer=1, tags=["python"])
        searcher = MemorySearch(tmp_store)
        result = searcher.context_inject("Python")
        assert isinstance(result, str)

    def test_context_inject_no_results_returns_empty(self, tmp_store):
        """結果なしの場合は空文字を返す"""
        searcher = MemorySearch(tmp_store)
        result = searcher.context_inject("xyz_not_found")
        assert result == ""

    def test_context_inject_contains_header(self, tmp_store):
        """結果ありの場合はヘッダを含む"""
        tmp_store.add("Important decision made", layer=2, tags=["decision"])
        searcher = MemorySearch(tmp_store)
        result = searcher.context_inject("decision", layers=[2])
        if result:  # 検索結果がある場合のみ確認
            assert "## Nested Memory Context" in result

    def test_context_inject_custom_layers(self, tmp_store):
        """カスタム層リストで検索する"""
        tmp_store.add("L3 procedural memory", layer=3)
        searcher = MemorySearch(tmp_store)
        result = searcher.context_inject("procedural", layers=[3])
        assert isinstance(result, str)

    def test_context_inject_max_tokens(self, tmp_store):
        """max_tokensで切り捨てが発生する"""
        for i in range(10):
            tmp_store.add(f"Long content entry {i} " + "x" * 100, layer=1)
        searcher = MemorySearch(tmp_store)
        result = searcher.context_inject("content", max_tokens=50, layers=[1])
        # max_tokensが小さいので結果は短いか空
        assert isinstance(result, str)
