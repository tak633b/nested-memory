"""
tests/test_store.py — NestedMemoryStore の基本テスト
add / search / stats を中心に MockLLM を使った pytest スタイルで検証
task#95: conftest.py の tmp_store / mock_llm フィクスチャを使用
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest

EXT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, EXT_DIR)

from nested_memory.store import NestedMemoryStore


# ─────────────────────────────────────────
# add / get
# ─────────────────────────────────────────

def test_add_returns_uuid(tmp_store):
    mem_id = tmp_store.add("テストメモリ", layer=1)
    assert isinstance(mem_id, str)
    assert len(mem_id) == 36  # uuid4 形式


def test_add_and_get_basic(tmp_store):
    mem_id = tmp_store.add("テストメモリ", layer=1, tags=["test"], importance=0.8)
    mem = tmp_store.get(mem_id)
    assert mem is not None
    assert mem.content == "テストメモリ"
    assert mem.layer == 1
    assert abs(mem.importance - 0.8) < 1e-6
    assert "test" in mem.tags


def test_add_default_tags_none_bug(tmp_store):
    """ミュータブルデフォルト引数バグが修正済みか確認 (task#91)"""
    id1 = tmp_store.add("first", layer=1)
    id2 = tmp_store.add("second", layer=1)
    m1 = tmp_store.get(id1)
    m2 = tmp_store.get(id2)
    # タグが空リストであること（前の呼び出しの影響を受けない）
    assert m1.tags == []
    assert m2.tags == []
    # 同じリストオブジェクトでないこと
    assert m1.tags is not m2.tags


def test_add_multiple_layers(tmp_store):
    tmp_store.add("L1記憶", layer=1)
    tmp_store.add("L2記憶", layer=2)
    tmp_store.add("L3記憶", layer=3)
    tmp_store.add("L4記憶", layer=4)
    counts = tmp_store.count_by_layer()
    assert counts[1] == 1
    assert counts[2] == 1
    assert counts[3] == 1
    assert counts[4] == 1


# ─────────────────────────────────────────
# search
# ─────────────────────────────────────────

def test_search_basic(tmp_store):
    tmp_store.add("Alice prefers visual learning styles", layer=2, tags=["person"])
    tmp_store.add("University campus facility management", layer=2, tags=["work"])
    results = tmp_store.search("Alice")
    assert len(results) > 0
    assert any("Alice" in r.content for r in results)


def test_search_layer_filter(tmp_store):
    tmp_store.add("L1の記憶", layer=1, tags=["l1"])
    tmp_store.add("L2の記憶", layer=2, tags=["l2"])
    results = tmp_store.search("記憶", layer=1)
    assert all(r.layer == 1 for r in results)


def test_search_no_results(tmp_store):
    tmp_store.add("関係ない内容", layer=1)
    results = tmp_store.search("存在しないキーワードxyz123")
    assert isinstance(results, list)
    # 0件でもエラーにならないこと


def test_search_compressed_excluded(tmp_store):
    mid = tmp_store.add("検索対象記憶", layer=1)
    tmp_store.mark_compressed([mid])
    results = tmp_store.search("検索対象記憶")
    # 圧縮済みは検索に出ない
    assert not any(r.id == mid for r in results)


# ─────────────────────────────────────────
# stats
# ─────────────────────────────────────────

def test_stats_empty(tmp_store):
    stats = tmp_store.stats()
    assert "total_active" in stats
    assert "total_compressed" in stats
    assert "by_layer" in stats
    assert "compression_runs" in stats
    assert "entity_count" in stats
    assert "db_path" in stats
    assert stats["total_active"] == 0


def test_stats_with_data(tmp_store):
    tmp_store.add("記憶1", layer=1)
    tmp_store.add("記憶2", layer=2)
    stats = tmp_store.stats()
    assert stats["total_active"] == 2
    # by_layer にL1/L2が含まれる
    layer_values = list(stats["by_layer"].values())
    assert sum(layer_values) == 2


def test_stats_compressed_count(tmp_store):
    mid = tmp_store.add("圧縮する記憶", layer=1)
    tmp_store.mark_compressed([mid])
    stats = tmp_store.stats()
    assert stats["total_compressed"] == 1
    assert stats["total_active"] == 0


# ─────────────────────────────────────────
# count_by_layer / get_by_layer
# ─────────────────────────────────────────

def test_count_by_layer(tmp_store):
    tmp_store.add("L1-1", layer=1)
    tmp_store.add("L2-1", layer=2)
    tmp_store.add("L2-2", layer=2)
    counts = tmp_store.count_by_layer()
    assert counts[1] == 1
    assert counts[2] == 2
    assert counts[3] == 0
    assert counts[4] == 0


def test_get_by_layer(tmp_store):
    tmp_store.add("L1-1", layer=1)
    tmp_store.add("L1-2", layer=1)
    tmp_store.add("L3記憶", layer=3)
    mems = tmp_store.get_by_layer(1)
    assert len(mems) == 2
    mems3 = tmp_store.get_by_layer(3)
    assert len(mems3) == 1


# ─────────────────────────────────────────
# mark_compressed
# ─────────────────────────────────────────

def test_mark_compressed(tmp_store):
    mid = tmp_store.add("圧縮対象", layer=1)
    tmp_store.mark_compressed([mid])
    mem = tmp_store.get(mid)
    assert mem.compressed == 1
    counts = tmp_store.count_by_layer()
    assert counts[1] == 0  # count_by_layerは圧縮済みを除外


# ─────────────────────────────────────────
# delete_expired
# ─────────────────────────────────────────

def test_delete_expired(tmp_store):
    # L4は期限なし
    tmp_store.add("期限なし", layer=4)
    # 期限切れをシミュレート（直接INSERT）
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    tmp_store._conn.execute(
        "INSERT INTO memories (id, layer, content, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), 1, "期限切れ", past, past),
    )
    tmp_store._conn.commit()
    deleted = tmp_store.delete_expired()
    assert deleted == 1
    # L4 は残っている
    stats = tmp_store.stats()
    assert stats["total_active"] == 1


# ─────────────────────────────────────────
# entities
# ─────────────────────────────────────────

def test_upsert_entity(tmp_store):
    tmp_store.upsert_entity("田中太郎", entity_type="person", layer=1)
    tmp_store.upsert_entity("田中太郎", layer=2)
    entities = tmp_store.get_entities(entity_type="person")
    assert len(entities) == 1
    assert entities[0].name == "田中太郎"
    assert "L1" in entities[0].layer_presence
    assert "L2" in entities[0].layer_presence


# ─────────────────────────────────────────
# compression_log
# ─────────────────────────────────────────

def test_compression_log(tmp_store):
    src_id = tmp_store.add("元記憶", layer=1)
    dst_id = tmp_store.add("圧縮後", layer=2)
    tmp_store.log_compression(1, 2, [src_id], dst_id, "claude-sonnet-4-6")
    logs = tmp_store.get_compression_log()
    assert len(logs) == 1
    assert logs[0]["from_layer"] == 1
    assert logs[0]["to_layer"] == 2


# ─────────────────────────────────────────
# MockLLM integration
# ─────────────────────────────────────────

def test_mock_llm_extract(mock_llm):
    entries = mock_llm.extract("今日の会議で重要な決定がありました")
    assert isinstance(entries, list)
    assert len(entries) > 0
    assert "content" in entries[0]
    assert entries[0]["importance"] >= 0.7


def test_mock_llm_compress(tmp_store, mock_llm):
    from nested_memory.layers import CompressionEngine
    id1 = tmp_store.add("記憶A", layer=1, importance=0.8)
    id2 = tmp_store.add("記憶B", layer=1, importance=0.9)
    mems = tmp_store.get_by_layer(1)
    engine = CompressionEngine(tmp_store, mock_llm)
    result = engine.compress_l1_to_l2(mems)
    assert result is not None
    assert result.layer == 2
    assert "mock-compressed" in result.content


def test_mock_llm_rerank(tmp_store, mock_llm):
    tmp_store.add("Alice is a visual learner", layer=1)
    tmp_store.add("University campus", layer=1)
    candidates = tmp_store.get_by_layer(1)
    reranked = mock_llm.rerank("Alice", candidates)
    assert len(reranked) == len(candidates)


# ─────────────────────────────────────────
# tag normalization (R3)
# ─────────────────────────────────────────

def test_normalize_tags_known():
    """TAG_NORMALIZATION内のキーが正規化されること"""
    from nested_memory.store import _normalize_tags, TAG_NORMALIZATION
    for raw, expected in TAG_NORMALIZATION.items():
        result = _normalize_tags([raw])
        assert result == [expected], f"Expected {raw!r} -> {expected!r}, got {result}"


def test_normalize_tags_unknown():
    """未知のタグはそのまま通ること"""
    from nested_memory.store import _normalize_tags
    unknown_tags = ["custom-tag", "my-label", "foo"]
    result = _normalize_tags(unknown_tags)
    assert result == unknown_tags


def test_add_normalizes_tags(tmp_store):
    """add() でタグが正規化されること"""
    mem_id = tmp_store.add("タグ正規化テスト", layer=1, tags=["L1", "L2-semantic"])
    mem = tmp_store.get(mem_id)
    assert "episodic" in mem.tags
    assert "semantic" in mem.tags
    assert "L1" not in mem.tags
    assert "L2-semantic" not in mem.tags


# ─────────────────────────────────────────
# deduplicate_similar (R1)
# ─────────────────────────────────────────

def test_deduplicate_dry_run(tmp_store):
    """重複候補が返るがDBは変わらないこと"""
    # 同一内容を2件追加（FTS5で高スコアになる）
    content = "Alice prefers visual learning styles and visual approaches"
    tmp_store.add(content, layer=1, importance=0.8)
    tmp_store.add(content, layer=1, importance=0.7)

    before_count = len(tmp_store.get_by_layer(1))
    results = tmp_store.deduplicate_similar(layer=1, threshold=0.1, dry_run=True)
    after_count = len(tmp_store.get_by_layer(1))

    # dry_run=True なのでDB件数は変わらない
    assert after_count == before_count
    # 候補リストは返る
    assert isinstance(results, list)
    for item in results:
        assert "kept" in item
        assert "removed" in item
        assert "score" in item
        assert item["merged"] is False


def test_deduplicate_empty_layer(tmp_store):
    """メモリが0-1件の場合は空リストを返す"""
    results = tmp_store.deduplicate_similar(layer=1, dry_run=True)
    assert results == []

    tmp_store.add("一件だけ", layer=1)
    results = tmp_store.deduplicate_similar(layer=1, dry_run=True)
    assert results == []
