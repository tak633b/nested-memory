"""
store.py — SQLite CRUD + FTS5検索
DBスキーマ初期化・記憶の追加・検索・管理
"""
import os
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional


DEFAULT_DB_PATH = os.path.expanduser("~/.openclaw/nested-memory.db")

LAYER_TTL_DAYS = {
    1: 7,    # L1 Episodic
    2: 90,   # L2 Semantic
    3: 365,  # L3 Procedural
    4: None, # L4 Meta (永続)
}

LAYER_NAMES = {
    1: "Episodic",
    2: "Semantic",
    3: "Procedural",
    4: "Meta",
}


@dataclass
class Memory:
    id: str
    layer: int
    content: str
    source: Optional[str] = None
    tags: list = field(default_factory=list)
    importance: float = 0.5
    created_at: str = ""
    expires_at: Optional[str] = None
    compressed: int = 0

    @property
    def layer_name(self) -> str:
        return LAYER_NAMES.get(self.layer, f"L{self.layer}")


@dataclass
class Entity:
    id: str
    name: str
    entity_type: Optional[str] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    layer_presence: dict = field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expires_iso(layer: int) -> Optional[str]:
    ttl = LAYER_TTL_DAYS.get(layer)
    if ttl is None:
        return None
    return (datetime.now(timezone.utc) + timedelta(days=ttl)).isoformat()


class NestedMemoryStore:
    """SQLiteベースの4層メモリストア"""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _migrate_schema(self):
        """既存DBのスキーマをrowid AUTOINCREMENT形式に移行"""
        c = self._conn
        # memories テーブルが旧スキーマ（id TEXT PRIMARY KEY のみ）かチェック
        cols = {row[1] for row in c.execute("PRAGMA table_info(memories)").fetchall()}
        if "rowid" not in cols and "id" in cols:
            # 旧スキーマ → 新スキーマへマイグレーション
            c.executescript("""
                ALTER TABLE memories RENAME TO memories_old;
                DROP INDEX IF EXISTS idx_memories_layer;
                DROP INDEX IF EXISTS idx_memories_compressed;
                DROP INDEX IF EXISTS idx_memories_created;
                CREATE TABLE memories (
                    rowid       INTEGER PRIMARY KEY AUTOINCREMENT,
                    id          TEXT NOT NULL UNIQUE,
                    layer       INTEGER NOT NULL,
                    content     TEXT NOT NULL,
                    source      TEXT,
                    tags        TEXT DEFAULT '[]',
                    importance  REAL DEFAULT 0.5,
                    created_at  TEXT NOT NULL,
                    expires_at  TEXT,
                    compressed  INTEGER DEFAULT 0
                );
                INSERT INTO memories (id, layer, content, source, tags, importance, created_at, expires_at, compressed)
                SELECT id, layer, content, source, tags, importance, created_at, expires_at, compressed
                FROM memories_old;
                DROP TABLE memories_old;
            """)
            # FTS再構築
            try:
                c.execute("INSERT INTO memories_fts(memories_fts) VALUES('rebuild')")
            except Exception:
                pass
            c.commit()

    def _init_schema(self):
        """DBスキーマの初期化"""
        c = self._conn
        c.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                rowid       INTEGER PRIMARY KEY AUTOINCREMENT,
                id          TEXT NOT NULL UNIQUE,
                layer       INTEGER NOT NULL,
                content     TEXT NOT NULL,
                source      TEXT,
                tags        TEXT DEFAULT '[]',
                importance  REAL DEFAULT 0.5,
                created_at  TEXT NOT NULL,
                expires_at  TEXT,
                compressed  INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS compression_log (
                id           TEXT PRIMARY KEY,
                from_layer   INTEGER,
                to_layer     INTEGER,
                source_ids   TEXT,
                result_id    TEXT,
                llm_model    TEXT,
                compressed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS entities (
                id            TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                entity_type   TEXT,
                first_seen    TEXT,
                last_seen     TEXT,
                layer_presence TEXT DEFAULT '{}'
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content, tags,
                content='memories', content_rowid='rowid'
            );

            CREATE INDEX IF NOT EXISTS idx_memories_layer ON memories(layer);
            CREATE INDEX IF NOT EXISTS idx_memories_compressed ON memories(compressed);
            CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
            CREATE INDEX IF NOT EXISTS idx_memories_expires ON memories(expires_at);
        """)
        c.commit()

        # 旧スキーマからのマイグレーション
        self._migrate_schema()

        # FTSトリガー（INSERT/UPDATE/DELETE時に自動更新）
        c.executescript("""
            CREATE TRIGGER IF NOT EXISTS memories_fts_insert
            AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content, tags)
                VALUES (new.rowid, new.content, new.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_fts_delete
            AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, tags)
                VALUES ('delete', old.rowid, old.content, old.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_fts_update
            AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, tags)
                VALUES ('delete', old.rowid, old.content, old.tags);
                INSERT INTO memories_fts(rowid, content, tags)
                VALUES (new.rowid, new.content, new.tags);
            END;
        """)
        c.commit()

    def _row_to_memory(self, row: sqlite3.Row) -> Memory:
        return Memory(
            id=row["id"],
            layer=row["layer"],
            content=row["content"],
            source=row["source"],
            tags=json.loads(row["tags"] or "[]"),
            importance=row["importance"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            compressed=row["compressed"],
        )

    def add(
        self,
        content: str,
        layer: int = 1,
        tags: Optional[list] = None,
        importance: float = 0.5,
        source: Optional[str] = None,
    ) -> str:
        """メモリを追加してIDを返す"""
        if tags is None:
            tags = []
        mem_id = str(uuid.uuid4())
        now = _now_iso()
        expires = _expires_iso(layer)
        self._conn.execute(
            """INSERT INTO memories (id, layer, content, source, tags, importance, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (mem_id, layer, content, source, json.dumps(tags), importance, now, expires),
        )
        self._conn.commit()
        return mem_id

    def get(self, mem_id: str) -> Optional[Memory]:
        """IDでメモリを取得"""
        row = self._conn.execute(
            "SELECT * FROM memories WHERE id = ?", (mem_id,)
        ).fetchone()
        return self._row_to_memory(row) if row else None

    def search(self, query: str, layer: Optional[int] = None, limit: int = 10) -> list:
        """FTS5全文検索 + LIKEフォールバック。layer指定時はその層のみ"""
        # FTS5クエリをエスケープ（特殊文字を含む可能性）
        escaped = query.replace('"', '""')
        sql = """
            SELECT m.* FROM memories m
            JOIN memories_fts f ON m.rowid = f.rowid
            WHERE memories_fts MATCH ?
              AND m.compressed = 0
        """
        params: list = [f'"{escaped}"']
        if layer is not None:
            sql += " AND m.layer = ?"
            params.append(layer)
        sql += " ORDER BY rank, m.importance DESC LIMIT ?"
        params.append(limit)

        rows = []
        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            pass

        # FTS5で0件またはエラーの場合はLIKEフォールバック（CJK・日本語対応）
        if not rows:
            sql2 = "SELECT * FROM memories WHERE compressed = 0 AND (content LIKE ? OR tags LIKE ?)"
            like_q = f"%{query}%"
            params2: list = [like_q, like_q]
            if layer is not None:
                sql2 += " AND layer = ?"
                params2.append(layer)
            sql2 += " ORDER BY importance DESC LIMIT ?"
            params2.append(limit)
            rows = self._conn.execute(sql2, params2).fetchall()

        return [self._row_to_memory(r) for r in rows]

    def get_by_layer(self, layer: int, include_compressed: bool = False) -> list:
        """指定層の記憶一覧を取得（TTL期限切れ除外）"""
        now = _now_iso()
        sql = """SELECT * FROM memories WHERE layer = ?
                 AND (expires_at IS NULL OR expires_at > ?)"""
        params = [layer, now]
        if not include_compressed:
            sql += " AND compressed = 0"
        sql += " ORDER BY importance DESC, created_at DESC"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def count_by_layer(self) -> dict:
        """各層のメモリ件数（未圧縮・有効のみ）"""
        now = _now_iso()
        rows = self._conn.execute(
            """SELECT layer, COUNT(*) as cnt FROM memories
               WHERE compressed = 0 AND (expires_at IS NULL OR expires_at > ?)
               GROUP BY layer""",
            (now,),
        ).fetchall()
        result = {1: 0, 2: 0, 3: 0, 4: 0}
        for r in rows:
            result[r["layer"]] = r["cnt"]
        return result

    def mark_compressed(self, ids: list):
        """指定IDのメモリを圧縮済みにマーク"""
        if not ids:
            return
        placeholders = ",".join("?" * len(ids))
        self._conn.execute(
            f"UPDATE memories SET compressed = 1 WHERE id IN ({placeholders})",  # nosec B608
            ids,
        )
        self._conn.commit()

    def log_compression(
        self,
        from_layer: int,
        to_layer: int,
        source_ids: list,
        result_id: str,
        llm_model: str,
    ):
        """圧縮ログを記録"""
        log_id = str(uuid.uuid4())
        self._conn.execute(
            """INSERT INTO compression_log (id, from_layer, to_layer, source_ids, result_id, llm_model, compressed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (log_id, from_layer, to_layer, json.dumps(source_ids), result_id, llm_model, _now_iso()),
        )
        self._conn.commit()

    def get_compression_log(self, limit: int = 20) -> list:
        """圧縮ログの取得"""
        rows = self._conn.execute(
            "SELECT * FROM compression_log ORDER BY compressed_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Entities ---

    def upsert_entity(
        self,
        name: str,
        entity_type: Optional[str] = None,
        layer: Optional[int] = None,
    ):
        """エンティティを追加または更新"""
        now = _now_iso()
        existing = self._conn.execute(
            "SELECT * FROM entities WHERE name = ?", (name,)
        ).fetchone()

        if existing:
            lp = json.loads(existing["layer_presence"] or "{}")
            if layer:
                key = f"L{layer}"
                lp[key] = lp.get(key, 0) + 1
            self._conn.execute(
                "UPDATE entities SET last_seen = ?, layer_presence = ? WHERE name = ?",
                (now, json.dumps(lp), name),
            )
        else:
            eid = str(uuid.uuid4())
            lp = {}
            if layer:
                lp[f"L{layer}"] = 1
            self._conn.execute(
                """INSERT INTO entities (id, name, entity_type, first_seen, last_seen, layer_presence)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (eid, name, entity_type, now, now, json.dumps(lp)),
            )
        self._conn.commit()

    def get_entities(self, entity_type: Optional[str] = None) -> list:
        """エンティティ一覧取得"""
        if entity_type:
            rows = self._conn.execute(
                "SELECT * FROM entities WHERE entity_type = ? ORDER BY last_seen DESC",
                (entity_type,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM entities ORDER BY last_seen DESC"
            ).fetchall()
        result = []
        for r in rows:
            result.append(Entity(
                id=r["id"],
                name=r["name"],
                entity_type=r["entity_type"],
                first_seen=r["first_seen"],
                last_seen=r["last_seen"],
                layer_presence=json.loads(r["layer_presence"] or "{}"),
            ))
        return result

    def delete_expired(self) -> int:
        """期限切れメモリを削除。削除件数を返す"""
        now = _now_iso()
        cur = self._conn.execute(
            "DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at < ?", (now,)
        )
        self._conn.commit()
        return cur.rowcount

    def stats(self) -> dict:
        """統計情報を返す"""
        counts = self.count_by_layer()
        now = _now_iso()
        total = self._conn.execute(
            "SELECT COUNT(*) FROM memories WHERE compressed = 0 AND (expires_at IS NULL OR expires_at > ?)",
            (now,)
        ).fetchone()[0]
        compressed_total = self._conn.execute(
            "SELECT COUNT(*) FROM memories WHERE compressed = 1"
        ).fetchone()[0]
        compression_count = self._conn.execute(
            "SELECT COUNT(*) FROM compression_log"
        ).fetchone()[0]
        entity_count = self._conn.execute(
            "SELECT COUNT(*) FROM entities"
        ).fetchone()[0]
        return {
            "total_active": total,
            "total_compressed": compressed_total,
            "by_layer": {
                f"L{k} ({LAYER_NAMES[k]})": v for k, v in counts.items()
            },
            "compression_runs": compression_count,
            "entity_count": entity_count,
            "db_path": self.db_path,
        }

    def close(self):
        self._conn.close()
