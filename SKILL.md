---
name: nested-memory
description: >
  4層ネステッドメモリシステム（Episodic→Semantic→Procedural→Meta）でAIの長期記憶を管理するスキル。
  会話から重要情報を自動抽出してL1（Episodic）に保存し、LLMによる圧縮で上位層へ蒸留。
  SQLite+FTS5によるハイブリッド検索、エンティティ追跡、自動圧縮スケジューラを備える。
  NeurIPS 2025論文「Nested Learning」(arXiv:2512.24695) に着想を得た実装。
  Claude Code MCP・OpenClaw extensionの両方として動作可能。
license: MIT
compatibility:
  openclaw: ">=1.0.0"
  claude-code: ">=1.0.0"
allowed-tools: exec Read Write Edit web_search
metadata:
  version: "0.1.0"
  author: "nested-memory contributors"
  tags:
    - memory
    - mcp
    - nested-learning
    - sqlite
triggers:
  - "過去の記憶を検索"
  - "記憶を保存"
  - "nested memory"
  - "4層メモリ"
  - "記憶を圧縮"
  - "エピソード記憶"
  - "手続き記憶"
  - "長期記憶"
  - "memory add"
  - "memory search"
capabilities:
  - memory_add
  - memory_search
  - memory_compress
  - memory_stats
  - entity_tracking
dependencies:
  - python3
  - anthropic>=0.86.0
  - sqlite3 (stdlib)
---

# Nested Memory Skill

## いつこのスキルを使うか

以下のトリガーに該当する場合にこのスキルを適用してください：

- ユーザーが「記憶を保存して」「覚えておいて（永続的に）」と言った時
- 過去の会話・決定事項・学習内容を検索・参照したい時
- セッションをまたいで記憶を引き継ぎたい時（コンパクション対策）
- エンティティ（人物・案件・設定値）のプロフィールを管理したい時
- 定期的な記憶圧縮・結晶化を自動化したい時

**適用しない場合**: 一時的なメモ（会話内のみで完結）、ファイルシステムへの直接保存で十分なケース

## 概要

4層ネステッドメモリシステム。会話の記憶を「揮発性の連続体」として管理:

```
L4: META        ── 自己モデル・進化履歴          [永続・手動]
L3: PROCEDURAL  ── 結晶化パターン・教訓          [月次圧縮]
L2: SEMANTIC    ── 抽出された事実・決定事項       [日次圧縮]
L1: EPISODIC    ── 生の観察・会話フラグメント      [セッション終了時]
```

## インストール方法

### OpenClaw Extension として

```bash
# リポジトリをextensionsディレクトリに配置
cp -r nested-memory/ ~/.openclaw/extensions/

# プラグインを有効化
openclaw plugins enable nested-memory

# 確認
openclaw plugins list
```

### Claude Code MCP として

`~/.claude/claude_desktop_config.json` に以下を追加：

```json
{
  "mcpServers": {
    "nested-memory": {
      "command": "python3",
      "args": ["/Users/<yourname>/.openclaw/extensions/nested-memory/mcp_server.py"],
      "env": {
        "ANTHROPIC_API_KEY": "<your-api-key>",
        "NESTED_MEMORY_DB": "/Users/<yourname>/.openclaw/nested-memory.db"
      }
    }
  }
}
```

Claude Code を再起動すると MCP ツールが利用可能になります。

## 使い方（CLI）

```bash
# メモリ追加（L1 Episodic）
python cli.py add "重要な記憶内容" --layer 1 --tags "tag1,tag2" --importance 0.8

# 上位層に追加（L2 Semantic）
python cli.py add "確定した事実" --layer 2 --importance 0.9

# 全文検索（FTS5）
python cli.py search "クエリ" --limit 5

# 特定レイヤーのみ検索
python cli.py search "クエリ" --layer 2 --limit 5

# 統計情報
python cli.py stats

# 圧縮実行（LLMが必要）
python cli.py compress --from-layer 1 --force

# エンティティ一覧
python cli.py entities --type person

# 会話テキストからL1を自動生成（LLMが必要）
python cli.py extract "会話テキスト"
```

## ファイル構成

```
nested-memory/
├── openclaw.plugin.json    # OpenClaw manifest
├── mcp_server.py           # Claude Code MCP server
├── index.js                # OpenClaw hooks
├── cli.py                  # CLI tool
├── nested_memory/
│   ├── store.py            # SQLite CRUD + FTS5
│   ├── llm.py              # LLM抽象レイヤー
│   ├── layers.py           # 圧縮エンジン
│   ├── search.py           # ハイブリッド検索
│   └── scheduler.py        # 自動圧縮スケジューラ
└── tests/                  # テスト
```

## 設定

`openclaw.plugin.json` の `configSchema` 参照:

| キー | 型 | デフォルト | 説明 |
|------|-----|-----------|------|
| `autoCapture` | bool | true | セッション終了時に自動抽出 |
| `autoRecall` | bool | true | セッション開始時に関連記憶を注入 |
| `autoCompress` | bool | true | cron時に自動圧縮 |
| `dbPath` | string | `~/.openclaw/nested-memory.db` | DBファイルパス |
| `extractionModel` | string | `claude-haiku-4-5` | 抽出モデル |
| `compressionModel` | string | `claude-sonnet-4-6` | 圧縮モデル |

## LLMモデル

| 用途 | モデル |
|------|--------|
| L1抽出（セッション末） | claude-haiku-4-5 |
| L1→L2圧縮 | claude-sonnet-4-6 |
| L2→L3圧縮 | claude-sonnet-4-6 |
| L3→L4圧縮 | claude-sonnet-4-6 |
| 検索リランク | claude-haiku-4-5 |

## MCPツール（Claude Code向け）

| ツール名 | 説明 |
|---------|------|
| `nested_memory_add` | 記憶を追加 |
| `nested_memory_search` | FTS5全文検索 |
| `nested_memory_compress` | 圧縮実行 |
| `nested_memory_stats` | 統計情報取得 |
| `nested_memory_entities` | エンティティ一覧 |

## 論文参照

Nested Learning (NeurIPS 2025, arXiv:2512.24695)
- Short-context flow → L1 Episodic
- Associative memory module → L2 Semantic
- Deep memory → L3 Procedural
- Self-modifying update algorithm → L4 Meta
