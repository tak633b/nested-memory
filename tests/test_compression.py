"""
tests/test_compression.py — 圧縮ロジックのテスト（LLMはモック）
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

EXT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, EXT_DIR)

from nested_memory.store import NestedMemoryStore
from nested_memory.layers import CompressionEngine, AutoCompressionScheduler


def make_mock_llm(compress_result="圧縮されたメモリ"):
    """LLMモック"""
    llm = MagicMock()
    llm.compress.return_value = compress_result
    llm.compress_model = "mock-model"
    return llm


class TestCompressionEngine(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.store = NestedMemoryStore(self.tmp.name)

    def tearDown(self):
        self.store.close()
        os.unlink(self.tmp.name)

    def test_compress_l1_to_l2(self):
        # L1記憶を3件追加
        ids = [self.store.add(f"エピソード{i}", layer=1, importance=0.8) for i in range(3)]
        memories = [self.store.get(mid) for mid in ids]

        llm = make_mock_llm("統合されたセマンティック記憶")
        engine = CompressionEngine(self.store, llm)

        result = engine.compress_l1_to_l2(memories)
        self.assertIsNotNone(result)
        self.assertEqual(result.layer, 2)
        self.assertEqual(result.content, "統合されたセマンティック記憶")

        # 元のL1は圧縮済みになっているはず
        for mid in ids:
            mem = self.store.get(mid)
            self.assertEqual(mem.compressed, 1)

        # 圧縮ログが記録されているはず
        logs = self.store.get_compression_log()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["from_layer"], 1)
        self.assertEqual(logs[0]["to_layer"], 2)

    def test_compress_l2_to_l3(self):
        ids = [self.store.add(f"セマンティック{i}", layer=2, importance=0.7) for i in range(2)]
        memories = [self.store.get(mid) for mid in ids]

        llm = make_mock_llm("手続き化されたパターン")
        engine = CompressionEngine(self.store, llm)

        result = engine.compress_l2_to_l3(memories)
        self.assertIsNotNone(result)
        self.assertEqual(result.layer, 3)
        self.assertEqual(result.content, "手続き化されたパターン")

    def test_compress_requires_llm(self):
        ids = [self.store.add("テスト", layer=1)]
        memories = [self.store.get(ids[0])]

        engine = CompressionEngine(self.store, llm=None)
        with self.assertRaises(RuntimeError):
            engine.compress_l1_to_l2(memories)

    def test_compress_empty_returns_none(self):
        llm = make_mock_llm()
        engine = CompressionEngine(self.store, llm)
        result = engine.compress_l1_to_l2([])
        self.assertIsNone(result)


class TestAutoCompressionScheduler(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.store = NestedMemoryStore(self.tmp.name)

    def tearDown(self):
        self.store.close()
        os.unlink(self.tmp.name)

    def test_check_below_threshold(self):
        """閾値未満なら圧縮しない"""
        for i in range(10):
            self.store.add(f"記憶{i}", layer=1)

        llm = make_mock_llm()
        scheduler = AutoCompressionScheduler(self.store, llm)
        results = scheduler.check_and_compress(verbose=False)
        # 10件 < 閾値50 → 圧縮なし
        self.assertEqual(results.get(1, 0), 0)

    def test_compress_layer_now_force(self):
        """force=True で閾値未満でも圧縮"""
        for i in range(3):
            self.store.add(f"記憶{i}", layer=1, importance=0.8)

        llm = make_mock_llm("強制圧縮結果")
        scheduler = AutoCompressionScheduler(self.store, llm)
        result = scheduler.compress_layer_now(1, force=True)
        self.assertIsNotNone(result)
        self.assertEqual(result.layer, 2)

    def test_compress_layer_now_no_force(self):
        """force=False で閾値未満なら圧縮しない"""
        for i in range(3):
            self.store.add(f"記憶{i}", layer=1)

        llm = make_mock_llm()
        scheduler = AutoCompressionScheduler(self.store, llm)
        result = scheduler.compress_layer_now(1, force=False)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
