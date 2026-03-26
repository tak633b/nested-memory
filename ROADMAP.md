# nested-memory Roadmap

> Last updated: 2026-03-26  
> Maintained by: BALTECH team (バルテック)

---

## ✅ v0.1.0 — Released (2026-03-26)

**Milestone: MVP Public Release**

- 4-layer SQLite memory (L1 Episodic → L4 Meta)
- Claude Code MCP server integration
- OpenClaw extension (same DB, shared context)
- Full-text search via FTS5
- LLM compression via Claude Haiku/Sonnet
- launchd daily (3:00 AM) + weekly (Mon 3:30 AM) scheduler
- 83 tests, 94% coverage
- ruff / mypy / bandit: 0 errors

---

## 🚀 v0.2.0 — Planned (Target: 2026-04 mid)

**Milestone: Stability & Usability**

### Bug Fixes & UX

- [ ] **install.sh idempotency fix** — Prevent duplicate launchd plist registration on re-install; add clean uninstall flow

### CJK / Search

- [ ] **FTS5 trigram tokenizer** (R2) — Replace `unicode61` with trigram mode (SQLite 3.44+) for proper Japanese/Chinese/Korean full-text search. Includes DB migration script.

### Resilience

- [ ] **LLM offline fallback mode** (R1) — Rule-based L1→L2 promotion when Anthropic API is unavailable; read-only mode without API key

### Configuration

- [ ] **`nested-memory.toml` config file** — Replaces CLI flags (`--no-auto-l4`). Manages: auto-l4, compression thresholds, model selection, DB path. Searched at `./nested-memory.toml` → `~/.config/nested-memory.toml`

### CLI / DX

- [ ] **`nm` shorthand command** — Install as `nm` to PATH; colorized output (importance levels, layer badges); `nm search` with optional fzf integration

### Testing

- [ ] **E2E test: MCP server startup + JSONRPC** — CI-runnable end-to-end test that starts `mcp_server.py` and validates at least one tool call round-trip

### Benchmarks

- [ ] **LoCoMo benchmark (or equivalent)** (R3) — Measure recall accuracy and latency; publish results in README with comparison notes

---

## 🗓 v0.2.x Patches (post-v0.2.0)

- **DB auto-backup + integrity check** — Weekly `.db.bak` copy via launchd; periodic `PRAGMA integrity_check` on FTS5 index

---

## 🌐 v0.3.0 — Planned (Target: 2026-06 end)

**Milestone: Real-World Integration & Breaking Change Window**

### Breaking Changes (bundled in v0.3.0)

- **MCP tool namespace rename** — `memory_add` → `nm_add`, `memory_search` → `nm_search`, etc. to avoid collisions with other MCP servers

### Real-World Integrations

- **Email-to-memory pipeline** — Cron script that reads `emails.db` and auto-adds key decisions/reply-pending items to L1
- **Obsidian / Markdown export** — `nm export` command: dump L2/L3 memories as Markdown files into a target directory (e.g., Vault)

### Infrastructure

- **MCP 2025 streamable HTTP transport** (investigation sprint in April) — Evaluate adoption timeline and design for SSE/streamable HTTP based on Claude Code roadmap

### CI / Quality

- **Benchmark regression in CI** — Run LoCoMo benchmark on every PR; fail if recall drops below baseline

---

## 🔮 v0.4.0+ — Future Directions

*Not yet scheduled. Ideas under consideration.*

- **Structured entity memory** — First-class support for named entities (people, project codes, decisions) with structured query (e.g., `nm entity "大西氏"`)
- **Tag auto-suggestion** — LLM proposes relevant tags at `nm add` time
- **Multi-DB / workspace profiles** — Separate memory DBs per project or persona
- **Plugin API** — Allow OpenClaw skills to register custom L1 ingestion hooks
- **Vector hybrid search** — Optional local embeddings (nomic-embed-text via Ollama) for semantic similarity search alongside FTS5

---

## Version Policy

| Version | Meaning |
|---------|---------|
| `v0.X.0` | Minor feature release (new functionality) |
| `v0.X.Y` | Patch release (bug fixes, docs, no breaking changes) |
| `v1.0.0` | Stable API; breaking changes require major version bump |

> **Breaking changes** are bundled into minor releases during `v0.x` phase and announced in CHANGELOG.md.

---

## Contributing

See [CHANGELOG.md](./CHANGELOG.md) for release history.  
Issues and PRs welcome: https://github.com/tak633b/nested-memory
