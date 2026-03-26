"""
tests/test_layers.py — CompressionEngine & AutoCompressionScheduler テスト
task#98: カバレッジ≥80%達成のための追加テスト
"""
import pytest
from nested_memory.layers import CompressionEngine, AutoCompressionScheduler


class TestCompressionEngine:
    """CompressionEngine の各メソッドのテスト"""

    def test_compress_requires_llm_when_no_llm(self, tmp_store):
        """LLMなしで圧縮するとRuntimeErrorを投げる"""
        engine = CompressionEngine(tmp_store, llm=None)
        # メモリを追加
        tmp_store.add("test memory", layer=1)
        memories = tmp_store.get_by_layer(1)
        with pytest.raises(RuntimeError, match="LLM is required"):
            engine.compress_l1_to_l2(memories)

    def test_compress_empty_returns_none(self, tmp_store, mock_llm):
        """空リストを渡すとNoneを返す"""
        engine = CompressionEngine(tmp_store, llm=mock_llm)
        result = engine.compress_l1_to_l2([])
        assert result is None

    def test_compress_l1_to_l2(self, tmp_store, mock_llm):
        """L1→L2圧縮が正常に動作する"""
        engine = CompressionEngine(tmp_store, llm=mock_llm)
        tmp_store.add("memory one", layer=1, tags=["a"])
        tmp_store.add("memory two", layer=1, tags=["b"])
        memories = tmp_store.get_by_layer(1)
        result = engine.compress_l1_to_l2(memories)
        assert result is not None
        assert result.layer == 2
        assert "[mock-compressed:L2]" in result.content

    def test_compress_l2_to_l3(self, tmp_store, mock_llm):
        """L2→L3圧縮が正常に動作する"""
        engine = CompressionEngine(tmp_store, llm=mock_llm)
        tmp_store.add("semantic memory", layer=2)
        memories = tmp_store.get_by_layer(2)
        result = engine.compress_l2_to_l3(memories)
        assert result is not None
        assert result.layer == 3

    def test_compress_l3_to_l4(self, tmp_store, mock_llm):
        """L3→L4圧縮が正常に動作する"""
        engine = CompressionEngine(tmp_store, llm=mock_llm)
        tmp_store.add("procedural memory", layer=3)
        memories = tmp_store.get_by_layer(3)
        result = engine.compress_l3_to_l4(memories)
        assert result is not None
        assert result.layer == 4

    def test_compress_layer_invalid_from_l4(self, tmp_store, mock_llm):
        """L4からの圧縮はValueErrorを投げる"""
        engine = CompressionEngine(tmp_store, llm=mock_llm)
        tmp_store.add("meta memory", layer=4)
        memories = tmp_store.get_by_layer(4)
        with pytest.raises(ValueError, match="top layer"):
            engine.compress_layer(4, memories)

    def test_compress_marks_source_as_compressed(self, tmp_store, mock_llm):
        """圧縮後、元のメモリはcompressed=Trueになる"""
        engine = CompressionEngine(tmp_store, llm=mock_llm)
        tmp_store.add("to be compressed", layer=1)
        memories = tmp_store.get_by_layer(1)
        assert len(memories) == 1
        engine.compress_l1_to_l2(memories)
        # L1の非圧縮メモリが0になるはず
        remaining = tmp_store.get_by_layer(1)
        assert len(remaining) == 0

    def test_compress_tags_merged(self, tmp_store, mock_llm):
        """圧縮結果のタグは元のタグのunionになる"""
        engine = CompressionEngine(tmp_store, llm=mock_llm)
        tmp_store.add("memory A", layer=1, tags=["alpha", "beta"])
        tmp_store.add("memory B", layer=1, tags=["beta", "gamma"])
        memories = tmp_store.get_by_layer(1)
        result = engine.compress_l1_to_l2(memories)
        assert result is not None
        assert "alpha" in result.tags
        assert "beta" in result.tags
        assert "gamma" in result.tags

    def test_compress_importance_max(self, tmp_store, mock_llm):
        """圧縮結果の重要度は元の最大値になる"""
        engine = CompressionEngine(tmp_store, llm=mock_llm)
        tmp_store.add("low importance", layer=1, importance=0.3)
        tmp_store.add("high importance", layer=1, importance=0.9)
        memories = tmp_store.get_by_layer(1)
        result = engine.compress_l1_to_l2(memories)
        assert result is not None
        assert result.importance == pytest.approx(0.9)


class TestAutoCompressionScheduler:
    """AutoCompressionScheduler のテスト"""

    def test_check_and_compress_no_action_when_below_threshold(self, tmp_store, mock_llm):
        """閾値未満の場合は圧縮されない"""
        scheduler = AutoCompressionScheduler(tmp_store, llm=mock_llm)
        # L1に5件だけ（閾値50未満）
        for i in range(5):
            tmp_store.add(f"memory {i}", layer=1)
        results = scheduler.check_and_compress(verbose=False)
        assert results.get(1, 0) == 0

    def test_check_and_compress_compresses_when_above_threshold(self, tmp_store, mock_llm):
        """閾値超過時に圧縮が実行される"""
        scheduler = AutoCompressionScheduler(tmp_store, llm=mock_llm)
        # L1に51件追加（閾値50超）
        for i in range(51):
            tmp_store.add(f"memory {i}", layer=1)
        results = scheduler.check_and_compress(verbose=False)
        assert results.get(1, 0) > 0

    def test_compress_layer_now_returns_none_when_empty(self, tmp_store, mock_llm):
        """メモリがない場合はNoneを返す"""
        scheduler = AutoCompressionScheduler(tmp_store, llm=mock_llm)
        result = scheduler.compress_layer_now(1)
        assert result is None

    def test_compress_layer_now_force(self, tmp_store, mock_llm):
        """force=Trueで閾値に関わらず圧縮する"""
        scheduler = AutoCompressionScheduler(tmp_store, llm=mock_llm)
        tmp_store.add("force compress this", layer=1)
        result = scheduler.compress_layer_now(1, force=True)
        assert result is not None
        assert result.layer == 2

    def test_compress_layer_now_no_force_below_threshold(self, tmp_store, mock_llm):
        """force=Falseで閾値未満の場合はNoneを返す"""
        scheduler = AutoCompressionScheduler(tmp_store, llm=mock_llm)
        # L1に少数だけ追加
        for i in range(3):
            tmp_store.add(f"memory {i}", layer=1)
        result = scheduler.compress_layer_now(1, force=False)
        assert result is None


# ─────────────────────────────────────────
# v0.1.2 threshold check
# ─────────────────────────────────────────

def test_default_threshold_l1_is_30():
    """THRESHOLDS[1] == 30 を確認 (v0.1.2)"""
    assert AutoCompressionScheduler.THRESHOLDS[1] == 30
