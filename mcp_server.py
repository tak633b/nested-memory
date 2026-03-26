#!/usr/bin/env python3
"""
mcp_server.py — Claude Code MCP Server (stdio transport)
Nested Memory の全機能をMCPツールとして公開

MCPツール一覧:
  nested_memory_add(content, layer?, tags?, importance?)
  nested_memory_search(query, layer?, limit?)
  nested_memory_compress(from_layer?, force?)
  nested_memory_stats()
  nested_memory_entities(entity_type?)
"""
import os
import sys
import json
import traceback
import threading
import uuid
import time
from typing import Any, Optional

# パス設定
EXT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EXT_DIR)

from nested_memory.store import NestedMemoryStore, DEFAULT_DB_PATH, LAYER_NAMES  # noqa: E402

# DB初期化（グローバル）
_store: Optional[NestedMemoryStore] = None
_llm = None

# 非同期ジョブ管理
_jobs: dict = {}  # job_id -> {"status": ..., "result": ..., "error": ..., "started_at": ...}


def get_store() -> NestedMemoryStore:
    global _store
    if _store is None:
        db_path = os.environ.get("NESTED_MEMORY_DB", DEFAULT_DB_PATH)
        _store = NestedMemoryStore(db_path)
    return _store


def get_llm():
    global _llm
    if _llm is None:
        try:
            from nested_memory.llm import MemoryLLM
            _llm = MemoryLLM()
        except RuntimeError:
            _llm = None
    return _llm


# --- MCPメッセージ送受信 ---

def send_response(msg: dict):
    """stdout にJSON-RPCレスポンスを書き出す"""
    print(json.dumps(msg, ensure_ascii=False), flush=True)


def make_error(code: int, message: str, data: Any = None) -> dict:
    err = {"code": code, "message": message}
    if data:
        err["data"] = data
    return err


# --- MCPツール定義 ---

TOOLS = [
    {
        "name": "nested_memory_add",
        "description": "記憶を指定層に追加する。layer=1(Episodic)がデフォルト。",
        "inputSchema": {
            "type": "object",
            "required": ["content"],
            "properties": {
                "content": {"type": "string", "description": "記憶内容"},
                "layer": {"type": "integer", "description": "層番号 1-4 (default: 1)", "minimum": 1, "maximum": 4},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "タグリスト"},
                "importance": {"type": "number", "description": "重要度 0.0-1.0 (default: 0.5)", "minimum": 0.0, "maximum": 1.0},
                "source": {"type": "string", "description": "ソース識別子"},
            },
        },
    },
    {
        "name": "nested_memory_search",
        "description": "FTS5全文検索で記憶を検索する。",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "description": "検索クエリ"},
                "layer": {"type": "integer", "description": "層フィルタ (1-4)", "minimum": 1, "maximum": 4},
                "limit": {"type": "integer", "description": "最大件数 (default: 5)", "minimum": 1, "maximum": 50},
            },
        },
    },
    {
        "name": "nested_memory_compress",
        "description": "指定層のメモリをバックグラウンドで非同期圧縮する（LLMが必要）。即座に job_id を返す。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_layer": {"type": "integer", "description": "圧縮元層 (1-3)", "minimum": 1, "maximum": 3},
                "force": {"type": "boolean", "description": "閾値未満でも強制実行"},
                "timeout_seconds": {"type": "integer", "description": "タイムアウト秒数 (default: 30)", "minimum": 1, "maximum": 300},
            },
        },
    },
    {
        "name": "nested_memory_compress_status",
        "description": "compress ジョブの進捗を確認する。",
        "inputSchema": {
            "type": "object",
            "required": ["job_id"],
            "properties": {
                "job_id": {"type": "string", "description": "compress が返した job_id"},
            },
        },
    },
    {
        "name": "nested_memory_stats",
        "description": "メモリの統計情報を返す（件数、圧縮回数、エンティティ数など）。",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "nested_memory_entities",
        "description": "追跡されているエンティティ（人物・プロジェクト等）の一覧を返す。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "description": "タイプフィルタ (person/project/concept/procedure)",
                    "enum": ["person", "project", "concept", "procedure"],
                },
            },
        },
    },
]


# --- ツール実装 ---

def tool_add(params: dict) -> dict:
    store = get_store()
    mem_id = store.add(
        content=params["content"],
        layer=params.get("layer", 1),
        tags=params.get("tags", []),
        importance=params.get("importance", 0.5),
        source=params.get("source"),
    )
    layer = params.get("layer", 1)
    return {
        "id": mem_id,
        "layer": layer,
        "layer_name": LAYER_NAMES.get(layer, f"L{layer}"),
        "message": f"記憶を追加しました: {mem_id[:16]}...",
    }


def tool_search(params: dict) -> dict:
    store = get_store()
    results = store.search(
        query=params["query"],
        layer=params.get("layer"),
        limit=params.get("limit", 5),
    )
    return {
        "count": len(results),
        "results": [
            {
                "id": m.id,
                "layer": m.layer,
                "layer_name": m.layer_name,
                "content": m.content,
                "tags": m.tags,
                "importance": m.importance,
                "created_at": m.created_at[:10],
            }
            for m in results
        ],
    }


def _run_compress_job(job_id: str, params: dict, timeout_seconds: int):
    """バックグラウンドスレッドで圧縮を実行する"""
    _jobs[job_id]["status"] = "running"
    deadline = time.time() + timeout_seconds

    try:
        llm = get_llm()
        if llm is None:
            _jobs[job_id].update({"status": "failed", "error": "LLMが利用できません。ANTHROPIC_API_KEY を設定してください。"})
            return

        store = get_store()
        from nested_memory.layers import AutoCompressionScheduler
        scheduler = AutoCompressionScheduler(store, llm)

        from_layer = params.get("from_layer")
        force = params.get("force", False)

        if time.time() > deadline:
            _jobs[job_id].update({"status": "failed", "error": f"タイムアウト ({timeout_seconds}秒)"})
            return

        if from_layer:
            result = scheduler.compress_layer_now(from_layer, force=force)
            if result:
                job_result = {
                    "compressed": True,
                    "from_layer": from_layer,
                    "to_layer": from_layer + 1,
                    "new_memory_id": result.id,
                    "content_preview": result.content[:200],
                }
            else:
                job_result = {"compressed": False, "message": "圧縮スキップ（対象なし or 閾値未満）"}
        else:
            results = scheduler.check_and_compress(verbose=False)
            total = sum(results.values())
            job_result = {
                "compressed": total > 0,
                "total_compressed": total,
                "by_layer": {f"L{k}": v for k, v in results.items()},
            }

        if time.time() > deadline:
            _jobs[job_id].update({"status": "failed", "error": f"タイムアウト ({timeout_seconds}秒)"})
            return

        _jobs[job_id].update({"status": "done", "result": job_result})

    except Exception as e:
        _jobs[job_id].update({"status": "failed", "error": str(e)})


def tool_compress(params: dict) -> dict:
    job_id = str(uuid.uuid4())
    timeout_seconds = params.get("timeout_seconds", 30)

    _jobs[job_id] = {
        "status": "pending",
        "result": None,
        "error": None,
        "started_at": time.time(),
        "params": {
            "from_layer": params.get("from_layer"),
            "force": params.get("force", False),
        },
    }

    t = threading.Thread(
        target=_run_compress_job,
        args=(job_id, params, timeout_seconds),
        daemon=True,
    )
    t.start()

    return {
        "status": "compression_started",
        "job_id": job_id,
        "timeout_seconds": timeout_seconds,
        "message": f"圧縮をバックグラウンドで開始しました。job_id: {job_id}",
    }


def tool_compress_status(params: dict) -> dict:
    job_id = params.get("job_id", "")
    if job_id not in _jobs:
        return {
            "status": "not_found",
            "job_id": job_id,
            "error": "指定された job_id が見つかりません",
        }

    job = _jobs[job_id]
    elapsed = time.time() - job["started_at"]

    response = {
        "job_id": job_id,
        "status": job["status"],  # pending / running / done / failed
        "elapsed_seconds": round(elapsed, 1),
    }

    if job["status"] == "done":
        response["result"] = job["result"]
    elif job["status"] == "failed":
        response["error"] = job["error"]

    return response


def tool_stats(params: dict) -> dict:
    store = get_store()
    return store.stats()


def tool_entities(params: dict) -> dict:
    store = get_store()
    entities = store.get_entities(entity_type=params.get("entity_type"))
    return {
        "count": len(entities),
        "entities": [
            {
                "id": e.id,
                "name": e.name,
                "entity_type": e.entity_type,
                "first_seen": e.first_seen[:10] if e.first_seen else None,
                "last_seen": e.last_seen[:10] if e.last_seen else None,
                "layer_presence": e.layer_presence,
            }
            for e in entities
        ],
    }


TOOL_HANDLERS = {
    "nested_memory_add": tool_add,
    "nested_memory_search": tool_search,
    "nested_memory_compress": tool_compress,
    "nested_memory_compress_status": tool_compress_status,
    "nested_memory_stats": tool_stats,
    "nested_memory_entities": tool_entities,
}


# --- MCP プロトコルハンドラ ---

def handle_request(req: dict) -> Optional[dict]:
    """JSON-RPCリクエストを処理してレスポンスを返す"""
    req_id = req.get("id")
    method = req.get("method", "")
    params = req.get("params", {})

    # Notification（id なし）は応答不要
    is_notification = req_id is None

    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "nested-memory",
                    "version": "1.0.0",
                },
            }

        elif method == "initialized":
            # Notification
            return None

        elif method == "tools/list":
            result = {"tools": TOOLS}

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_input = params.get("arguments", {})

            if tool_name not in TOOL_HANDLERS:
                if is_notification:
                    return None
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": make_error(-32601, f"Unknown tool: {tool_name}"),
                }

            tool_result = TOOL_HANDLERS[tool_name](tool_input)
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(tool_result, ensure_ascii=False, indent=2),
                    }
                ]
            }

        elif method == "ping":
            result = {}

        else:
            if is_notification:
                return None
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": make_error(-32601, f"Method not found: {method}"),
            }

        if is_notification:
            return None

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result,
        }

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[MCP] Error handling {method}: {e}\n{tb}", file=sys.stderr)
        if is_notification:
            return None
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": make_error(-32603, str(e), tb),
        }


def main():
    """stdio トランスポートのメインループ"""
    print("[nested-memory MCP server] Started", file=sys.stderr)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            send_response({
                "jsonrpc": "2.0",
                "id": None,
                "error": make_error(-32700, f"Parse error: {e}"),
            })
            continue

        response = handle_request(req)
        if response is not None:
            send_response(response)


if __name__ == "__main__":
    main()
