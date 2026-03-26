"""
tests/conftest.py — 共通フィクスチャとモック定義
task#95: MockLLM クラス + tmp_store フィクスチャ
"""
import os
import sys
import pytest

EXT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, EXT_DIR)

from nested_memory.store import NestedMemoryStore


class MockLLM:
    """
    テスト用LLMモック。
    実際のAPIを呼ばず、決定的なレスポンスを返す。
    """
    extract_model = "mock-extract"
    compress_model = "mock-compress"

    def extract(self, session_text: str) -> list:
        """会話テキストから記憶エントリを抽出するモック"""
        return [
            {
                "content": f"[mock] {session_text[:50]}",
                "tags": ["mock", "test"],
                "importance": 0.8,
            }
        ]

    def compress(self, memories, target_layer: int) -> str:
        """記憶圧縮のモック"""
        contents = " / ".join(m.content[:30] for m in memories)
        return f"[mock-compressed:L{target_layer}] {contents}"

    def rerank(self, query: str, candidates) -> list:
        """リランクのモック（順序そのまま返す）"""
        return candidates


@pytest.fixture
def tmp_store(tmp_path):
    """
    一時ファイルDBを使ったNestedMemoryStoreフィクスチャ。
    :memory: は FTS5 トリガーとの互換性問題があるためファイルDBを使用。
    """
    db_file = tmp_path / "test_nested_memory.db"
    store = NestedMemoryStore(str(db_file))
    yield store
    store.close()


@pytest.fixture
def mock_llm():
    """MockLLMインスタンスを返すフィクスチャ"""
    return MockLLM()
