"""
search.py — FTS5ハイブリッド検索
BM25 / FTS5 + 重要度ブースト
"""
from typing import Optional
from .store import NestedMemoryStore


class MemorySearch:
    """FTS5 + 重要度ブーストによるハイブリッド検索"""

    def __init__(self, store: NestedMemoryStore):
        self.store = store

    def search(
        self,
        query: str,
        layer: Optional[int] = None,
        limit: int = 10,
        llm=None,
        rerank: bool = False,
    ) -> list:
        """
        FTS5検索 + オプショナルLLMリランク
        """
        results = self.store.search(query, layer=layer, limit=limit * 2 if rerank else limit)

        if rerank and llm and results:
            results = llm.rerank(query, results)
            results = results[:limit]
        else:
            results = results[:limit]

        return results

    def search_by_tags(self, tags: list, layer: Optional[int] = None, limit: int = 10) -> list:
        """タグ検索（FTS5のtags列を使用）"""
        if not tags:
            return []
        query = " OR ".join(tags)
        return self.store.search(query, layer=layer, limit=limit)

    def context_inject(
        self,
        query: str,
        max_tokens: int = 2000,
        layers: Optional[list] = None,
    ) -> str:
        """
        エージェントコンテキストに注入するメモリ文字列を生成
        max_tokens: 概算文字数上限
        """
        if layers is None:
            layers = [3, 2, 1]  # 高層→低層の順で優先

        injected = []
        total_chars = 0

        for layer in layers:
            results = self.search(query, layer=layer, limit=5)
            for mem in results:
                entry = f"[L{layer} {mem.layer_name}] {mem.content}"
                if total_chars + len(entry) > max_tokens:
                    break
                injected.append(entry)
                total_chars += len(entry)

        if not injected:
            return ""

        return "## Nested Memory Context\n" + "\n".join(injected)
