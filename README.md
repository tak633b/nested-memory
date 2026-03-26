# Nested Memory Plugin

4層ネステッドメモリシステム for OpenClaw / Claude Code MCP

論文参照: **Nested Learning** (NeurIPS 2025, arXiv:2512.24695)

## アーキテクチャ

```
L4: META        ── 自己モデル・進化履歴            [永続・手動管理]
L3: PROCEDURAL  ── 結晶化パターン・ワークフロー     [月次圧縮]
L2: SEMANTIC    ── 抽出された事実・決定事項         [日次圧縮]
L1: EPISODIC    ── 生の観察・会話フラグメント        [セッション終了時]
         ↑ 各層はLLMによる "compression function" で上位に蒸留
```

## セットアップ

### クイックインストール（推奨）
```bash
cd ~/.openclaw/extensions/nested-memory
./install.sh
```

`install.sh` が行うこと:
1. `~/.openclaw/extensions/nested-memory/` への配置確認
2. DBスキーマ初期化 (`nested_memory/store.py --init`)
3. launchd plist を `~/Library/LaunchAgents/` に配置してロード

#### launchd ジョブ（自動圧縮スケジュール）
| ジョブ | スケジュール | 実行内容 |
|--------|------------|---------|
| `com.baltech.nested-memory.daily` | 毎日 3:00 AM | `python3 cli.py compress --layer 1`（L1→L2） |
| `com.baltech.nested-memory.weekly` | 毎週月曜 3:30 AM | `python3 cli.py compress --layer 2`（L2→L3） |

ログ: `~/.openclaw/logs/nested-memory-daily.log` / `nested-memory-weekly.log`

手動で再インストール/更新する場合:
```bash
# plist のみ再ロード
launchctl unload ~/Library/LaunchAgents/com.baltech.nested-memory.daily.plist
launchctl load   ~/Library/LaunchAgents/com.baltech.nested-memory.daily.plist

# 手動実行テスト
launchctl start com.baltech.nested-memory.daily
```

### OpenClaw Extension
```bash
openclaw plugins enable nested-memory
```

### Claude Code MCP

Claude Code（またはClaude Desktop）からMCPサーバーとして使用できます。

#### Step 1: リポジトリをクローン
```bash
git clone https://github.com/tak633b/nested-memory.git ~/.openclaw/extensions/nested-memory
cd ~/.openclaw/extensions/nested-memory
pip install anthropic
python3 nested_memory/store.py --init
```

#### Step 2: MCP設定を追加

**Claude Code** (`~/.claude.json` または `claude mcp add` コマンド):
```bash
claude mcp add nested-memory python3 /path/to/nested-memory/mcp_server.py
```

または手動で `~/.claude.json` を編集:
```json
{
  "mcpServers": {
    "nested-memory": {
      "command": "python3",
      "args": ["/path/to/nested-memory/mcp_server.py"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

**Claude Desktop** (`claude_desktop_config.json`):
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "nested-memory": {
      "command": "python3",
      "args": ["/path/to/nested-memory/mcp_server.py"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

#### Step 3: 動作確認

Claude CodeまたはClaude Desktopを再起動後、以下のように使えます:

```
# Claude Codeでの使用例
> memory_add content="Learned about FTS5 full-text search in SQLite" layer=1 tags=["sqlite","search"]
> memory_search query="SQLite" layer=2
> memory_compress layer=1          # L1→L2に圧縮（バックグラウンド実行）
> memory_compress_status job_id=<id>  # 圧縮の進捗確認
> memory_stats
```

#### 利用可能なMCPツール

| ツール | 説明 |
|--------|------|
| `memory_add` | メモリを指定層に追加 |
| `memory_search` | 全文検索（FTS5）でメモリを検索 |
| `memory_compress` | LLMで指定層を上位層に圧縮（非同期） |
| `memory_compress_status` | 圧縮ジョブの進捗確認 |
| `memory_stats` | 層ごとのメモリ統計を表示 |
| `memory_list` | 指定層のメモリ一覧 |
| `memory_entities` | エンティティ（人物・概念）一覧 |

## CLI使い方

```bash
# メモリ追加
python cli.py add "Alice prefers visual learning" --layer 2 --tags "person,profile" --importance 0.9

# 全文検索
python cli.py search "Alice" --layer 2 --limit 5

# 統計表示
python cli.py stats

# 指定層の一覧
python cli.py list --layer 1

# LLMで会話からL1を自動抽出
python cli.py extract "会話テキスト..."

# 圧縮実行（LLM必要）
python cli.py compress --from-layer 1
python cli.py compress --from-layer 1 --force  # 強制実行

# エンティティ一覧
python cli.py entities --type person

# 期限切れを削除
python cli.py delete-expired
```

## テスト

```bash
cd ~/.openclaw/extensions/nested-memory
python3 -m pytest tests/ -v
```

## 依存関係

- Python 3.9+
- anthropic >= 0.86.0
- sqlite3 (stdlib)

## DB

デフォルト: `~/.openclaw/nested-memory.db`

カスタムパスを指定する場合:
```bash
# CLI
python3 cli.py stats --db /path/to/my-memory.db

# MCP環境変数で指定
"env": {
  "NESTED_MEMORY_DB": "/path/to/my-memory.db",
  "ANTHROPIC_API_KEY": "sk-ant-..."
}
```

---

## Claude Codeでの使用例

MCP設定後、Claude Codeのセッション内で自然言語・ツール直接呼び出しの両方で使えます。

### 基本的な使い方

```
# 会話内容をL1（Episodic）に記録
Use memory_add to store: "Decided to use SQLite over PostgreSQL for zero-dependency deployment"
→ layer=1, tags=["decision","architecture"]

# キーワードで検索
Use memory_search to find memories about "SQLite"

# 統計確認
Use memory_stats
```

### 会話からの自動抽出 → 圧縮フロー

```
# Step 1: 会話テキストからL1を自動抽出
Use memory_add to extract key facts from this conversation:
"We discussed three options for storage: SQLite, PostgreSQL, and DynamoDB.
 We chose SQLite because it requires zero infrastructure and fits our local-first philosophy."

# Step 2: L1が溜まったらL2へ圧縮（LLM要約）
Use memory_compress with layer=1

# Step 3: 圧縮の完了を確認
Use memory_compress_status with job_id=<returned_id>

# Step 4: 圧縮後の結果を検索
Use memory_search with query="storage decision" layer=2
```

### プロジェクト横断での記憶管理

```
# プロジェクトAの決定をタグ付きで保存
Use memory_add: "Project A: selected React + TypeScript for frontend"
→ layer=1, tags=["project-a","frontend","decision"], importance=0.8

# プロジェクトBの学習を保存
Use memory_add: "Project B: learned that FTS5 trigram tokenizer is needed for CJK search"
→ layer=1, tags=["project-b","sqlite","lesson"], importance=0.9

# タグで絞り込み検索
Use memory_search: query="decision" tags=["project-a"]

# エンティティ（人物・概念）一覧
Use memory_entities with type="concept"
```

### `.clauderc` / `CLAUDE.md` との組み合わせ

プロジェクトの `CLAUDE.md` に以下を追記することで、Claude Codeが自動的にメモリを活用します:

```markdown
## Memory
Use the `nested-memory` MCP tools to:
- Store important decisions with `memory_add` (layer=2, importance≥0.8)
- Search past context with `memory_search` before answering questions about prior work
- After long sessions, compress L1 memories with `memory_compress`
```
