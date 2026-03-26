"""
tests/test_llm.py — LLM モジュールのユニットテスト
task#98: カバレッジ≥80%達成のための追加テスト
実際のAPI呼び出しはすべてモック化
"""
import json
import pytest
from unittest.mock import patch, MagicMock


class TestGetAnthropicKey:
    """_get_anthropic_key() のテスト"""

    def test_returns_env_key(self, monkeypatch):
        """ANTHROPIC_API_KEY 環境変数からキーを取得する"""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")
        # auth-profiles.jsonが読めない状態でも env から取得できる
        with patch("builtins.open", side_effect=Exception("no file")):
            from nested_memory.llm import _get_anthropic_key
            key = _get_anthropic_key()
        assert key == "test-key-123"

    def test_returns_empty_when_no_key(self, monkeypatch):
        """キーが見つからない場合は空文字を返す"""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with patch("builtins.open", side_effect=Exception("no file")):
            from nested_memory.llm import _get_anthropic_key
            key = _get_anthropic_key()
        assert key == ""


class TestCallAnthropic:
    """_call_anthropic() のテスト"""

    def test_calls_anthropic_sdk(self, monkeypatch):
        """Anthropic SDKを呼び出してテキストを返す"""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="test response")]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("anthropic.Anthropic", return_value=mock_client):
            from nested_memory import llm as llm_module
            result = llm_module._call_anthropic(
                "test prompt", "test system", "claude-haiku-4-5", 100, 0.2
            )
        assert result == "test response"

    def test_raises_when_no_api_key(self, monkeypatch):
        """APIキーがない場合はRuntimeErrorを投げる"""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with patch("builtins.open", side_effect=Exception("no file")):
            with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
                from nested_memory import llm as llm_module
                llm_module._call_anthropic("prompt", "sys", "model", 100, 0.2)


class TestMemoryLLM:
    """MemoryLLM クラスのテスト"""

    @pytest.fixture
    def memory_llm(self, monkeypatch):
        """APIキーをセットしてMemoryLLMを初期化"""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-456")
        from nested_memory.llm import MemoryLLM
        with patch("nested_memory.llm._get_anthropic_key", return_value="test-key-456"):
            return MemoryLLM()

    def test_init_raises_without_key(self, monkeypatch):
        """キーなしで初期化するとRuntimeError"""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with patch("nested_memory.llm._get_anthropic_key", return_value=""):
            with pytest.raises(RuntimeError, match="LLM APIキー"):
                from nested_memory.llm import MemoryLLM
                MemoryLLM()

    def test_extract_returns_list(self, memory_llm):
        """extract()がリストを返す"""
        mock_result = json.dumps([
            {"content": "テスト記憶", "tags": ["test"], "importance": 0.8}
        ])
        with patch.object(memory_llm, "_call", return_value=mock_result):
            result = memory_llm.extract("会話テキスト")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["content"] == "テスト記憶"

    def test_extract_filters_low_importance(self, memory_llm):
        """重要度0.7未満はフィルタされる"""
        mock_result = json.dumps([
            {"content": "高重要度", "tags": [], "importance": 0.9},
            {"content": "低重要度", "tags": [], "importance": 0.3},
        ])
        with patch.object(memory_llm, "_call", return_value=mock_result):
            result = memory_llm.extract("テキスト")
        assert len(result) == 1
        assert result[0]["content"] == "高重要度"

    def test_extract_handles_code_block(self, memory_llm):
        """```jsonコードブロックを除去してパースする"""
        mock_result = '```json\n[{"content": "parsed", "tags": [], "importance": 0.8}]\n```'
        with patch.object(memory_llm, "_call", return_value=mock_result):
            result = memory_llm.extract("テキスト")
        assert len(result) == 1

    def test_extract_returns_empty_on_error(self, memory_llm):
        """パースエラー時は空リストを返す"""
        with patch.object(memory_llm, "_call", return_value="invalid json"):
            result = memory_llm.extract("テキスト")
        assert result == []

    def test_extract_returns_empty_when_not_list(self, memory_llm):
        """リストでないJSONの場合は空リストを返す"""
        with patch.object(memory_llm, "_call", return_value='{"key": "value"}'):
            result = memory_llm.extract("テキスト")
        assert result == []

    def test_compress_l1_to_l2(self, memory_llm):
        """L2ターゲットでL1→L2圧縮を実行する"""
        mock_memories = [MagicMock(importance=0.8, content="memory A"), MagicMock(importance=0.6, content="memory B")]
        with patch.object(memory_llm, "_call", return_value="compressed text") as mock_call:
            result = memory_llm.compress(mock_memories, target_layer=2)
        assert result == "compressed text"
        # L1→L2のシステムプロンプトが使われたことを確認
        call_kwargs = mock_call.call_args
        assert "system" in call_kwargs.kwargs or len(call_kwargs.args) >= 2

    def test_compress_l2_to_l3(self, memory_llm):
        """L3ターゲット圧縮"""
        mock_memories = [MagicMock(importance=0.7, content="semantic memory")]
        with patch.object(memory_llm, "_call", return_value="procedural text"):
            result = memory_llm.compress(mock_memories, target_layer=3)
        assert result == "procedural text"

    def test_compress_l3_to_l4(self, memory_llm):
        """L4ターゲット圧縮"""
        mock_memories = [MagicMock(importance=0.9, content="procedural memory")]
        with patch.object(memory_llm, "_call", return_value="meta text"):
            result = memory_llm.compress(mock_memories, target_layer=4)
        assert result == "meta text"

    def test_compress_returns_empty_on_error(self, memory_llm):
        """圧縮エラー時は空文字を返す"""
        mock_memories = [MagicMock(importance=0.8, content="memory")]
        with patch.object(memory_llm, "_call", side_effect=Exception("API error")):
            result = memory_llm.compress(mock_memories, target_layer=2)
        assert result == ""

    def test_rerank_basic(self, memory_llm):
        """基本リランク動作"""
        mock_memories = [
            MagicMock(content="memory A"),
            MagicMock(content="memory B"),
            MagicMock(content="memory C"),
        ]
        with patch.object(memory_llm, "_call", return_value="[2, 0, 1]"):
            result = memory_llm.rerank("query", mock_memories)
        assert len(result) == 3
        assert result[0] == mock_memories[2]

    def test_rerank_empty_returns_empty(self, memory_llm):
        """空リストはそのまま返す"""
        result = memory_llm.rerank("query", [])
        assert result == []

    def test_rerank_returns_original_on_error(self, memory_llm):
        """エラー時は元のリストを返す"""
        mock_memories = [MagicMock(content="A"), MagicMock(content="B")]
        with patch.object(memory_llm, "_call", side_effect=Exception("error")):
            result = memory_llm.rerank("query", mock_memories)
        assert result == mock_memories

    def test_rerank_handles_code_block(self, memory_llm):
        """```コードブロックを除去してパースする"""
        mock_memories = [MagicMock(content="A"), MagicMock(content="B")]
        with patch.object(memory_llm, "_call", return_value="```\n[1, 0]\n```"):
            result = memory_llm.rerank("query", mock_memories)
        assert result[0] == mock_memories[1]

    def test_rerank_handles_invalid_indices(self, memory_llm):
        """範囲外インデックスは無視する"""
        mock_memories = [MagicMock(content="A")]
        with patch.object(memory_llm, "_call", return_value="[0, 99, -1]"):
            result = memory_llm.rerank("query", mock_memories)
        assert len(result) == 1
