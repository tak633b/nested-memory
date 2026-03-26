# Changelog

All notable changes to this project will be documented in this file.

## [0.1.1] - 2026-03-26

### Added
- `deduplicate_similar()`: FTS5 BM25-based deduplication (dry-run default)
- `nm dedupe` CLI command with `--threshold` and `--dry-run` flags

### Improved
- `EXTRACT_SYSTEM` prompt: added importance scoring distribution guide (0.1-1.0)
- `add()`: automatic tag normalization (e.g. "L1" -> "episodic")

## [0.1.0] - 2026-03-26

### Added

- **4層ネストメモリアーキテクチャ** — L1 Episodic / L2 Semantic / L3 Procedural / L4 Meta の階層構造（arXiv:2512.24695 "Nested Learning" 準拠）
- **SQLite + FTS5 ストレージ** — 外部依存なしのローカル単一ファイルDB。rowid分離スキーマで安全な並列アクセスに対応
- **LLM圧縮パイプライン** — L1→L2 自動抽出（claude-haiku-4-5）、L2→L3 圧縮蒸留（claude-sonnet-4-6）
- **CLIインターフェース** (`cli.py`) — `add` / `search` / `compress` / `list` / `stats` / `entities` / `delete-expired` コマンド + `--layer` エイリアス + `--dry-run` オプション
- **Claude Code MCP server** (`mcp_server.py`) — stdio プロトコル準拠。`memory_add` / `memory_search` / `memory_compress` / `memory_stats` ツール提供
- **OpenClaw Extension** (`index.js`, `openclaw.plugin.json`) — セッション終了フックでのL1自動記録、ハートビート連携
- **launchd スケジューラ** — 毎日 3:00 AM にL1→L2圧縮、毎週月曜 3:30 AM にL2→L3圧縮を自動実行
- **ハイブリッド検索** (`search.py`) — FTS5全文検索 × importanceスコアリングの複合検索
- **ワンライナーインストール** (`install.sh`) — DBスキーマ初期化 + launchd plist 自動配置
- **テストスイート** — 83テスト、カバレッジ 94%（ruff / mypy / bandit 全エラー0件）
- **AgentSkills準拠 SKILL.md** — OpenClaw スキル仕様に沿ったドキュメント

### Known Limitations

- FTS5 の CJK（日本語・中国語・韓国語）トークナイズ精度が低い（trigram / unicode61 トークナイザーへの移行を検討中）
- LoCoMo ベンチマークによる長期記憶評価は未実施（v0.2.0 予定）
- LLM API 障害時の劣化モード（LLM なし圧縮スキップ）は部分実装
