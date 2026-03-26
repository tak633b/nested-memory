#!/usr/bin/env python3
"""
cli.py — Nested Memory CLI
動作確認・手動操作用コマンドラインインターフェース

使い方:
    python cli.py add "覚えておきたいこと" [--layer 1] [--tags tag1,tag2] [--importance 0.8]
    python cli.py search "クエリ" [--layer 2] [--limit 5]
    python cli.py compress [--from-layer 1] [--force]
    python cli.py stats
    python cli.py entities [--type person]
    python cli.py extract "会話テキスト"   # LLMでL1エントリを自動生成
    python cli.py delete-expired          # 期限切れメモリを削除
"""
import os
import sys
import json
import argparse
from typing import Optional

# パス設定
EXT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EXT_DIR)

from nested_memory.store import NestedMemoryStore, DEFAULT_DB_PATH, LAYER_NAMES  # noqa: E402


def get_store(db_path: Optional[str] = None) -> NestedMemoryStore:
    return NestedMemoryStore(db_path or DEFAULT_DB_PATH)


def cmd_add(args):
    """メモリを追加"""
    store = get_store(args.db)
    layer = _resolve_layer(args.layer)
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
    mem_id = store.add(
        content=args.content,
        layer=layer,
        tags=tags,
        importance=args.importance,
        source=args.source,
    )
    print(f"✅ Added: {mem_id}")
    print(f"   Layer: L{layer} ({LAYER_NAMES.get(layer, '?')})")
    print(f"   Importance: {args.importance}")
    if tags:
        print(f"   Tags: {', '.join(tags)}")
    store.close()


def cmd_search(args):
    """FTS5全文検索"""
    store = get_store(args.db)
    layer = _resolve_layer(args.layer) if hasattr(args, 'layer') and args.layer else None
    results = store.search(args.query, layer=layer, limit=args.limit)

    if not results:
        print(f"🔍 No results for: {args.query!r}")
        store.close()
        return

    print(f"🔍 Found {len(results)} result(s) for: {args.query!r}")
    print()
    for i, mem in enumerate(results):
        print(f"[{i+1}] L{mem.layer} {mem.layer_name} | importance={mem.importance:.2f}")
        print(f"     {mem.content}")
        if mem.tags:
            print(f"     Tags: {', '.join(mem.tags)}")
        print(f"     ID: {mem.id[:16]}... | Created: {mem.created_at[:10]}")
        print()
    store.close()


def _resolve_layer(layer_arg) -> Optional[int]:
    """layer引数を数値に変換。数字(1-4)またはエイリアス名を受け付ける（task#94）"""
    if layer_arg is None:
        return None
    LAYER_ALIASES = {
        "episodic": 1,
        "semantic": 2,
        "procedural": 3,
        "meta": 4,
        "1": 1, "2": 2, "3": 3, "4": 4,
    }
    if isinstance(layer_arg, int):
        return layer_arg
    key = str(layer_arg).lower()
    if key in LAYER_ALIASES:
        return LAYER_ALIASES[key]
    raise ValueError(f"Invalid layer: {layer_arg!r}. Use 1/2/3/4 or episodic/semantic/procedural/meta")


def cmd_compress(args):
    """手動圧縮"""
    from_layer = _resolve_layer(args.from_layer) if args.from_layer else None
    force = args.force
    dry_run = getattr(args, "dry_run", False)

    store = get_store(args.db)

    # --dry-run: 件数とAPI呼び出し見積もりを表示してexit（task#94）
    if dry_run:
        from nested_memory.layers import AutoCompressionScheduler
        counts = store.count_by_layer()
        print("🔍 Compress --dry-run: 実行見積もり")
        print()
        if from_layer:
            layers_to_check = [(from_layer, counts.get(from_layer, 0))]
        else:
            layers_to_check = [(layer_key, counts.get(layer_key, 0)) for layer_key in sorted(AutoCompressionScheduler.THRESHOLDS.keys())]

        total_api_calls = 0
        for layer, count in layers_to_check:
            threshold = AutoCompressionScheduler.THRESHOLDS.get(layer, 0)
            excess = max(0, count - threshold)
            batch_size = AutoCompressionScheduler.BATCH_SIZE
            batches = (excess + batch_size - 1) // batch_size if excess > 0 else 0
            status = "🔴 圧縮対象" if excess > 0 else "✅ 閾値未満"
            from nested_memory.store import LAYER_NAMES
            print(f"  L{layer} {LAYER_NAMES.get(layer,'')}:")
            print(f"    現在: {count}件 / 閾値: {threshold}件 → {status}")
            if excess > 0:
                print(f"    圧縮対象: {excess}件 → {batches}バッチ × API呼び出し")
            total_api_calls += batches
        print()
        print(f"  推定API呼び出し数: {total_api_calls}回")
        store.close()
        sys.exit(0)

    # LLM初期化
    try:
        from nested_memory.llm import MemoryLLM
        llm = MemoryLLM()
    except RuntimeError as e:
        print(f"❌ LLM初期化エラー: {e}")
        store.close()
        sys.exit(1)

    from nested_memory.layers import AutoCompressionScheduler
    scheduler = AutoCompressionScheduler(store, llm)

    if from_layer:
        result = scheduler.compress_layer_now(from_layer, force=force)
        if result:
            print(f"✅ 圧縮完了: L{from_layer} → L{from_layer+1}")
            print(f"   New memory: {result.id[:16]}...")
            print(f"   Content: {result.content[:200]}")
        else:
            print("⚠️  圧縮スキップ（対象なし or 閾値未満）")
    else:
        # 全層チェック
        results = scheduler.check_and_compress(verbose=True)
        total = sum(results.values())
        if total > 0:
            print(f"\n✅ 圧縮完了: 合計 {total} 件を上位層に昇格")
        else:
            print("\n✅ 圧縮不要（全層閾値未満）")

    store.close()


def cmd_stats(args):
    """統計情報表示"""
    store = get_store(args.db)
    stats = store.stats()

    print("=" * 50)
    print("📊 Nested Memory Stats")
    print("=" * 50)
    print(f"DB: {stats['db_path']}")
    print()
    print(f"Active memories:     {stats['total_active']}")
    print(f"Compressed memories: {stats['total_compressed']}")
    print(f"Compression runs:    {stats['compression_runs']}")
    print(f"Tracked entities:    {stats['entity_count']}")
    print()
    print("By Layer:")
    for layer_name, count in stats['by_layer'].items():
        bar = "█" * min(count, 30) + ("" if count <= 30 else f"+{count-30}")
        print(f"  {layer_name:30s}: {count:4d}  {bar}")
    print("=" * 50)
    store.close()


def cmd_entities(args):
    """エンティティ一覧"""
    store = get_store(args.db)
    entity_type = args.type if hasattr(args, 'type') and args.type else None
    entities = store.get_entities(entity_type=entity_type)

    if not entities:
        print("エンティティなし")
        store.close()
        return

    print(f"👤 Entities ({len(entities)} total):")
    print()
    for e in entities:
        lp_str = json.dumps(e.layer_presence, ensure_ascii=False)
        print(f"  {e.name} [{e.entity_type or 'unknown'}]")
        print(f"    First: {e.first_seen[:10] if e.first_seen else '?'} | Last: {e.last_seen[:10] if e.last_seen else '?'}")
        print(f"    Layers: {lp_str}")
    store.close()


def cmd_extract(args):
    """LLMを使って会話テキストからL1エントリを自動生成"""
    try:
        from nested_memory.llm import MemoryLLM
        llm = MemoryLLM()
    except RuntimeError as e:
        print(f"❌ LLM初期化エラー: {e}")
        sys.exit(1)

    print("🤖 LLMで記憶を抽出中...")
    entries = llm.extract(args.text)

    if not entries:
        print("抽出結果なし（重要度0.7未満 or エラー）")
        return

    print(f"✅ {len(entries)}件抽出:")
    store = get_store(args.db)
    for entry in entries:
        content = entry.get("content", "")
        tags = entry.get("tags", [])
        importance = entry.get("importance", 0.7)
        mem_id = store.add(content=content, layer=1, tags=tags, importance=importance, source="cli:extract")
        print(f"  [{importance:.2f}] {content[:100]} → {mem_id[:16]}...")
    store.close()


def cmd_delete_expired(args):
    """期限切れメモリを削除"""
    store = get_store(args.db)
    deleted = store.delete_expired()
    print(f"🗑️  {deleted} 件の期限切れメモリを削除しました")
    store.close()


def cmd_list(args):
    """指定層のメモリ一覧"""
    store = get_store(args.db)
    layer = _resolve_layer(args.layer)
    memories = store.get_by_layer(layer)

    if not memories:
        print(f"L{layer} ({LAYER_NAMES.get(layer, '?')}) メモリなし")
        store.close()
        return

    print(f"📋 L{layer} {LAYER_NAMES.get(layer, '?')} ({len(memories)} items):")
    print()
    for mem in memories:
        print(f"  [{mem.importance:.2f}] {mem.content[:120]}")
        if mem.tags:
            print(f"         Tags: {', '.join(mem.tags)}")
        print(f"         {mem.id[:16]}... | {mem.created_at[:10]}")
    store.close()


def main():
    parser = argparse.ArgumentParser(
        description="Nested Memory CLI — 4層ネステッドメモリシステム",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py add "User is INFP-T" --layer 2 --tags "person,profile" --importance 0.9
  python cli.py search "Alice" --layer 2
  python cli.py stats
  python cli.py compress --from-layer 1 --force
  python cli.py list --layer 1
  python cli.py entities --type person
        """
    )
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help=f"DBパス (default: {DEFAULT_DB_PATH})")
    subparsers = parser.add_subparsers(dest="command")

    # add
    p_add = subparsers.add_parser("add", help="メモリを追加")
    p_add.add_argument("content", help="記憶内容")
    p_add.add_argument("--layer", default="1",
                       help="層番号またはエイリアス (1/2/3/4 または episodic/semantic/procedural/meta)")
    p_add.add_argument("--tags", default="", help="タグ（カンマ区切り）")
    p_add.add_argument("--importance", type=float, default=0.5, help="重要度 (0.0-1.0)")
    p_add.add_argument("--source", default=None, help="ソース識別子")

    # search
    p_search = subparsers.add_parser("search", help="全文検索")
    p_search.add_argument("query", help="検索クエリ")
    p_search.add_argument("--layer", default=None,
                          help="層フィルタ (1/2/3/4 または episodic/semantic/procedural/meta)")
    p_search.add_argument("--limit", type=int, default=5, help="最大件数")

    # compress
    p_compress = subparsers.add_parser("compress", help="圧縮実行")
    p_compress.add_argument("--from-layer", dest="from_layer", default=None,
                            help="圧縮元層 (1/2/3 または episodic/semantic/procedural)")
    p_compress.add_argument("--force", action="store_true", help="閾値未満でも強制実行")
    p_compress.add_argument("--dry-run", dest="dry_run", action="store_true",
                            help="件数とAPI呼び出し見積もりを表示してexit（実際には圧縮しない）")

    # stats
    subparsers.add_parser("stats", help="統計情報表示")

    # entities
    p_ent = subparsers.add_parser("entities", help="エンティティ一覧")
    p_ent.add_argument("--type", default=None, help="エンティティタイプフィルタ (person/project/concept/procedure)")

    # extract
    p_extract = subparsers.add_parser("extract", help="会話テキストからLLMでL1エントリを自動生成")
    p_extract.add_argument("text", help="会話テキスト")

    # delete-expired
    subparsers.add_parser("delete-expired", help="期限切れメモリを削除")

    # list
    p_list = subparsers.add_parser("list", help="指定層のメモリ一覧")
    p_list.add_argument("--layer", default="1",
                        help="層番号またはエイリアス (1/2/3/4 または episodic/semantic/procedural/meta)")

    args = parser.parse_args()

    if args.command == "add":
        cmd_add(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "compress":
        cmd_compress(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "entities":
        cmd_entities(args)
    elif args.command == "extract":
        cmd_extract(args)
    elif args.command == "delete-expired":
        cmd_delete_expired(args)
    elif args.command == "list":
        cmd_list(args)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
