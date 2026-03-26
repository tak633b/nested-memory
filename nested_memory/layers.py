"""
layers.py — 4層圧縮ロジック + 自動トリガー
CompressionEngine + AutoCompressionScheduler
"""
import sys
from typing import Optional
from .store import NestedMemoryStore, Memory, LAYER_NAMES


class CompressionEngine:
    """層間の圧縮処理"""

    def __init__(self, store: NestedMemoryStore, llm=None):
        self.store = store
        self.llm = llm

    def _require_llm(self):
        if self.llm is None:
            raise RuntimeError("LLM is required for compression. Pass llm= to CompressionEngine.")

    def _do_compress(self, memories: list, from_layer: int, to_layer: int) -> Optional[Memory]:
        """圧縮実行の共通処理"""
        if not memories:
            return None
        self._require_llm()

        compressed_text = self.llm.compress(memories, target_layer=to_layer)
        if not compressed_text:
            print(f"[CompressionEngine] LLM returned empty result for L{from_layer}→L{to_layer}", file=sys.stderr)
            return None

        # 重要度: 元記憶の最大値
        max_importance = max(m.importance for m in memories)
        # タグ: 元記憶のタグをunion
        all_tags = set()
        for m in memories:
            all_tags.update(m.tags)

        source_ids = [m.id for m in memories]
        source_label = f"compression:L{from_layer}→L{to_layer}:batch_{source_ids[0][:8]}"

        # 上位層に追加
        new_id = self.store.add(
            content=compressed_text,
            layer=to_layer,
            tags=sorted(all_tags),
            importance=max_importance,
            source=source_label,
        )

        # 元記憶を圧縮済みにマーク
        self.store.mark_compressed(source_ids)

        # 圧縮ログ記録
        model_name = getattr(self.llm, 'compress_model', 'unknown')
        self.store.log_compression(from_layer, to_layer, source_ids, new_id, model_name)

        return self.store.get(new_id)

    def compress_l1_to_l2(self, memories: list) -> Optional[Memory]:
        """L1 Episodic → L2 Semantic"""
        return self._do_compress(memories, from_layer=1, to_layer=2)

    def compress_l2_to_l3(self, memories: list) -> Optional[Memory]:
        """L2 Semantic → L3 Procedural"""
        return self._do_compress(memories, from_layer=2, to_layer=3)

    def compress_l3_to_l4(self, memories: list) -> Optional[Memory]:
        """L3 Procedural → L4 Meta"""
        return self._do_compress(memories, from_layer=3, to_layer=4)

    def compress_layer(self, from_layer: int, memories: list) -> Optional[Memory]:
        """層番号指定で圧縮"""
        to_layer = from_layer + 1
        if to_layer > 4:
            raise ValueError("L4 is the top layer, cannot compress further.")
        return self._do_compress(memories, from_layer=from_layer, to_layer=to_layer)


class AutoCompressionScheduler:
    """
    閾値監視 + 自動圧縮スケジューラ
    各層のメモリ数が閾値を超えたら自動圧縮
    """

    THRESHOLDS = {1: 50, 2: 100}  # L3→L4は意図しない自動昇格を防ぐため手動のみ（task#91）
    BATCH_SIZE = 20  # 1回の圧縮バッチサイズ

    def __init__(self, store: NestedMemoryStore, llm=None):
        self.store = store
        self.llm = llm
        self.engine = CompressionEngine(store, llm)

    def check_and_compress(self, verbose: bool = True) -> dict:
        """
        全層の閾値チェック → 超過分を自動圧縮
        返値: {layer: compressed_count}
        """
        results = {}
        counts = self.store.count_by_layer()

        for layer, threshold in self.THRESHOLDS.items():
            count = counts.get(layer, 0)
            if count <= threshold:
                if verbose:
                    print(f"[Scheduler] L{layer} ({LAYER_NAMES[layer]}): {count}/{threshold} — OK")
                results[layer] = 0
                continue

            to_compress = self.store.get_by_layer(layer)
            if not to_compress:
                continue

            compressed_total = 0
            # バッチ処理
            while len(to_compress) > threshold:
                batch = to_compress[:self.BATCH_SIZE]
                result = self.engine.compress_layer(layer, batch)
                if result:
                    compressed_total += len(batch)
                    if verbose:
                        print(f"[Scheduler] L{layer}→L{layer+1}: {len(batch)}件圧縮 → {result.id[:8]}...")
                else:
                    if verbose:
                        print(f"[Scheduler] L{layer} 圧縮失敗")
                    break
                # 再取得
                to_compress = self.store.get_by_layer(layer)

            results[layer] = compressed_total

        return results

    def compress_layer_now(self, from_layer: int, force: bool = False) -> Optional[Memory]:
        """
        指定層を即時圧縮（force=True で閾値無視）
        返値: 圧縮結果Memory or None
        """
        memories = self.store.get_by_layer(from_layer)
        if not memories:
            print(f"[Scheduler] L{from_layer}: メモリなし")
            return None

        threshold = self.THRESHOLDS.get(from_layer, 0)
        if not force and len(memories) <= threshold:
            print(f"[Scheduler] L{from_layer}: {len(memories)}/{threshold} — 閾値未満（--force で強制実行）")
            return None

        batch = memories[:self.BATCH_SIZE]
        return self.engine.compress_layer(from_layer, batch)
