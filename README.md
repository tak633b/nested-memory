# nested-memory

> Persistent, compressing long-term memory for Claude Code — via MCP.  
> Inspired by **Nested Learning** (NeurIPS 2025, [arXiv:2512.24695](https://arxiv.org/abs/2512.24695))

---

## The problem

Claude Code is great at tasks — but it forgets everything the moment a session ends.

You find yourself repeating the same context every time:

- *"We decided to use SQLite over Postgres — remember?"*
- *"The rate limit on that API is 100 req/min. I told you last week."*
- *"Our coding style is X. Stop suggesting Y."*

External memory tools exist, but they come with friction: a vector DB to run, an API to call, embeddings to maintain. Most teams give up and just paste context manually.

## The solution

`nested-memory` gives Claude Code **persistent, self-compressing long-term memory** — stored entirely in a single local SQLite file, no infrastructure required.

Memories are distilled upward through 4 layers automatically:

```
L4: META        — Self-model, system-level patterns     [auto, threshold: 30]
L3: PROCEDURAL  — Crystallized workflows, habits        [auto, threshold: 100]
L2: SEMANTIC    — Extracted facts, decisions            [auto, threshold: 50]
L1: EPISODIC    — Raw observations, conversation notes  [session-end]
         ↑ Each layer distilled by LLM "compression function"
```

> **L4 control:** Auto-compression is on by default. To keep L4 (Meta) manual:
> ```bash
> python3 cli.py compress --no-auto-l4
> ```

**Before nested-memory:**
```
Session 1: "We chose React. Rate limit is 100/min."
Session 2: [Claude has no memory of session 1]
Session 3: [Claude suggests Postgres again]
```

**After nested-memory:**
```
Session 1: memory_add "Chose React, rate limit 100/min" → L1
  → nightly compression: key facts promoted to L2 (Semantic)
Session 2: memory_search "architecture" → finds React decision instantly
Session 3: Claude already knows the constraints before you type them
```

**Key properties:**
- 🗄️ Zero infrastructure — single SQLite file, no server needed
- 🔍 Full-text search via SQLite FTS5 (no embeddings required)
- 🤖 LLM compression via Claude Haiku/Sonnet (Anthropic API)
- 🏷️ Tag + importance filtering for precise retrieval
- 🔌 Works as Claude Code MCP server **and** OpenClaw extension (same DB)
- 🧪 83 tests, 94% coverage

---

## Quickstart (Claude Code)

### Step 1: Clone & install

```bash
git clone https://github.com/tak633b/nested-memory.git
cd nested-memory
pip install anthropic
./install.sh
```

`install.sh` handles everything:
- DB schema initialization
- launchd jobs for background compression (macOS only)
- OpenClaw plugin registration (if `openclaw` is in your PATH)

### Step 2: Register as MCP server

```bash
claude mcp add nested-memory python3 /path/to/nested-memory/mcp_server.py
```

Or add manually to `~/.claude.json`:

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

### Step 3: Add to your project's `CLAUDE.md`

Paste this into your project's `CLAUDE.md` so Claude Code uses memory automatically:

```markdown
## Memory
Use the `nested-memory` MCP tools to:
- Store important decisions with `memory_add` (layer=2, importance≥0.8)
- Search past context with `memory_search` before answering questions about prior work
- After long sessions, compress L1 memories with `memory_compress`
```

That's it. Claude Code will now remember across sessions.

---

## Claude Desktop

Add to `claude_desktop_config.json`:

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

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `memory_add` | Add a memory to a specific layer |
| `memory_search` | Full-text search across memories |
| `memory_compress` | Compress a layer upward via LLM (async) |
| `memory_compress_status` | Check compression job progress |
| `memory_stats` | Show memory counts by layer |
| `memory_list` | List memories in a layer |
| `memory_entities` | List tracked entities (people, concepts) |

---

## Usage Examples

### Store a decision
```
Use memory_add to store:
"Chose SQLite over PostgreSQL — zero infrastructure, local-first"
→ layer=2, tags=["decision", "architecture"], importance=0.9
```

### Search past context
```
Use memory_search to find memories about "SQLite"
```

### Extract facts from a conversation
```
Use memory_add to extract key facts from this conversation:
"We discussed React vs Vue. Chose React for the larger ecosystem and team familiarity."
→ layer=1, tags=["decision", "frontend"]
```

### Compress L1 after a long session
```
Use memory_compress with layer=1
→ Returns job_id immediately (runs in background)

Use memory_compress_status with job_id=<id>
→ {"status": "done", "compressed": true, "new_memory_id": "..."}
```

### Project-scoped memory with tags
```
# Save
memory_add: "Project A: API rate limit is 100 req/min"
→ layer=1, tags=["project-a", "api"], importance=0.7

# Recall
memory_search: query="rate limit" tags=["project-a"]
```

---

## CLI (standalone use)

```bash
# Add
python3 cli.py add "Alice prefers visual learning" --layer 2 --tags "person,profile" --importance 0.9

# Search
python3 cli.py search "Alice" --layer 2 --limit 5

# Compress L1 → L2
python3 cli.py compress --from-layer 1

# Stats
python3 cli.py stats

# List by layer
python3 cli.py list --layer 1

# Entities
python3 cli.py entities --type person
```

`--layer` accepts both numbers (`1`) and names (`episodic`, `semantic`, `procedural`, `meta`).

---

## DB

Default path: `~/.nested-memory.db`

To use a custom path:
```bash
python3 cli.py stats --db /path/to/my-memory.db
```

Or set via MCP environment variable:
```json
"env": {
  "NESTED_MEMORY_DB": "/path/to/my-memory.db",
  "ANTHROPIC_API_KEY": "sk-ant-..."
}
```

> **Tip:** To scope memory per project, point `NESTED_MEMORY_DB` to a path inside your project directory (e.g. `./.nested-memory.db`). Add it to `.gitignore` to keep it local.

---

## Auto-compression (macOS launchd)

For automatic background compression, run `install.sh`:

```bash
./install.sh
```

This installs two launchd jobs:

| Job | Schedule | Action |
|-----|----------|--------|
| `com.baltech.nested-memory.daily` | Every day 3:00 AM | Compress L1 → L2 |
| `com.baltech.nested-memory.weekly` | Every Monday 3:30 AM | Compress L2 → L3 |

Logs: `~/.openclaw/logs/nested-memory-daily.log`

---

## Requirements

- Python 3.9+
- `anthropic >= 0.86.0`
- SQLite with FTS5 (included in macOS/Linux standard Python)

---

## Tests

```bash
python3 -m pytest tests/ -v
# 83 tests, 94% coverage
```

---

## OpenClaw (bonus)

If you use [OpenClaw](https://openclaw.ai), you can install this as a plugin directly from [ClaWHub](https://clawhub.com):

```bash
# ClaWHub経由でインストール
/plugin marketplace add tak633b/nested-memory
```

Or manually:
```bash
openclaw plugins enable nested-memory
```

The same SQLite DB is shared between the MCP server and the OpenClaw extension.

---

## License

MIT
