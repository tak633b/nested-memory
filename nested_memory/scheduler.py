"""
scheduler.py — 自動圧縮スケジューラ
cron/手動実行用エントリポイント
"""
import os
import sys
import json
import argparse
from datetime import datetime
from typing import Optional


# パス設定
EXT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, EXT_DIR)

from nested_memory.store import NestedMemoryStore, DEFAULT_DB_PATH  # noqa: E402
from nested_memory.layers import AutoCompressionScheduler  # noqa: E402


def get_llm(db_path: Optional[str] = None):
    """LLMクライアントの初期化（APIキーがない場合はNone）"""
    try:
        from nested_memory.llm import MemoryLLM
        return MemoryLLM()
    except RuntimeError as e:
        print(f"[Scheduler] LLM初期化失敗: {e}", file=sys.stderr)
        return None


def run_daily(db_path: str = DEFAULT_DB_PATH, verbose: bool = True) -> dict:
    """日次cron: L1→L2チェック"""
    store = NestedMemoryStore(db_path)
    llm = get_llm()
    scheduler = AutoCompressionScheduler(store, llm)

    if verbose:
        print(f"[DailyCron] {datetime.now().isoformat()} — L1→L2チェック開始")

    results = {}
    counts = store.count_by_layer()
    l1_count = counts.get(1, 0)
    threshold = AutoCompressionScheduler.THRESHOLDS[1]

    if l1_count > threshold:
        result = scheduler.check_and_compress(verbose=verbose)
        results = result
    else:
        if verbose:
            print(f"[DailyCron] L1: {l1_count}/{threshold} — 閾値未満、スキップ")

    store.delete_expired()
    if verbose:
        print("[DailyCron] 期限切れメモリを削除しました")

    store.close()
    return results


def run_weekly(db_path: str = DEFAULT_DB_PATH, verbose: bool = True) -> dict:
    """週次cron: L2→L3チェック"""
    store = NestedMemoryStore(db_path)
    llm = get_llm()
    scheduler = AutoCompressionScheduler(store, llm)

    if verbose:
        print(f"[WeeklyCron] {datetime.now().isoformat()} — L2→L3チェック開始")

    counts = store.count_by_layer()
    l2_count = counts.get(2, 0)
    threshold = AutoCompressionScheduler.THRESHOLDS[2]

    results = {}
    if l2_count > threshold:
        result = scheduler.check_and_compress(verbose=verbose)
        results = result
    else:
        if verbose:
            print(f"[WeeklyCron] L2: {l2_count}/{threshold} — 閾値未満、スキップ")

    store.close()
    return results


def main():
    parser = argparse.ArgumentParser(description="Nested Memory 自動圧縮スケジューラ")
    parser.add_argument("mode", choices=["daily", "weekly", "all"], help="実行モード")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="DBパス")
    parser.add_argument("--quiet", action="store_true", help="ログ抑制")

    args = parser.parse_args()
    verbose = not args.quiet

    if args.mode == "daily":
        results = run_daily(args.db, verbose=verbose)
    elif args.mode == "weekly":
        results = run_weekly(args.db, verbose=verbose)
    elif args.mode == "all":
        results = {}
        store = NestedMemoryStore(args.db)
        llm = get_llm()
        scheduler = AutoCompressionScheduler(store, llm)
        results = scheduler.check_and_compress(verbose=verbose)
        store.delete_expired()
        store.close()

    if verbose:
        print(f"[Scheduler] 完了: {json.dumps(results, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
