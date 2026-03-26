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
`claude_desktop_config.json` に追加:
```json
{
  "mcpServers": {
    "nested-memory": {
      "command": "python3",
      "args": ["/Users/YOUR_USER/.openclaw/extensions/nested-memory/mcp_server.py"],
      "env": { "ANTHROPIC_API_KEY": "sk-ant-..." }
    }
  }
}
```

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
