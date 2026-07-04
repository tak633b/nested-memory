# Security Policy

## Reporting a Vulnerability

Please report security issues privately via GitHub Security Advisories
(the "Security" tab of this repository) rather than opening a public issue.

## Scope and data handling

`nested-memory` stores captured memories in a local SQLite database at
`~/.nested-memory.db` and sends memory text to the Anthropic API for
extraction and compression. Be aware that:

- The database is unencrypted and readable by any process running as your user.
- Conversation content is transmitted to Anthropic when compression or
  extraction runs. Do not capture secrets or credentials into memory.
- The API key is read from `ANTHROPIC_API_KEY` or
  `~/.openclaw/agents/main/agent/auth-profiles.json`. Keep both out of version
  control.
