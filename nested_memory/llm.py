"""
llm.py — LLM abstraction layer
Direct Anthropic SDK + OpenClaw llm_client.py dual support
Provider auto-detection logic included
"""
import os
import json
import sys

EXTRACT_MODEL = "claude-haiku-4-5"
COMPRESS_MODEL = "claude-sonnet-4-6"


def _get_anthropic_key() -> str:
    """Retrieve API key: OpenClaw auth-profiles.json (priority) -> ANTHROPIC_API_KEY env var (fallback)
    task#92: Prioritize OpenClaw key (follows implementation pattern from scripts/llm_client.py)
    """
    # 1. OpenClaw auth-profiles.json (highest priority)
    # Try the main agent profile first
    for agent_name in ("main",):
        profiles_path = os.path.expanduser(
            f"~/.openclaw/agents/{agent_name}/agent/auth-profiles.json"
        )
        try:
            with open(profiles_path) as f:
                d = json.load(f)
            token = d.get("profiles", {}).get("anthropic:default", {}).get("token", "")
            if token:
                return token
        except Exception:
            pass

    # 2. ANTHROPIC_API_KEY environment variable (fallback)
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key

    return ""


def _call_anthropic(
    prompt: str,
    system: str,
    model: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """Call Anthropic SDK directly"""
    import anthropic

    api_key = _get_anthropic_key()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not found. Set env var or configure auth-profiles.json.")

    client = anthropic.Anthropic(api_key=api_key)
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    resp = client.messages.create(**kwargs)  # type: ignore[call-overload]
    return resp.content[0].text


# --- Prompt definitions ---

EXTRACT_SYSTEM = """You are an AI that extracts important memory entries from conversations.
Extract memory-worthy entries from the following conversation text.
Extraction criteria:
- Decisions made (something was decided, approved)
- Proper nouns (names, project names, tool names)
- Numerical data (amounts, dates, percentages)
- Tasks and action items
- Emotionally significant events
- Discoveries of procedures or methods

Output format: JSON array only. No explanatory text.
[{"content": "memory content (1-2 sentences)", "tags": ["tag1", "tag2"], "importance": 0.0-1.0}]
Only extract entries with importance >= 0.7 (noise reduction)."""

L1_TO_L2_SYSTEM = """You are an AI that compresses episodic memories into semantic memories.
Integrate and compress the following episodic memories (conversation fragments) semantically.
Requirements:
- Always preserve specific proper nouns, numbers, and dates
- Remove duplicate and redundant information
- Output as a single integrated semantic memory
Output: Compressed memory text only (no explanation)"""

L2_TO_L3_SYSTEM = """You are an AI that extracts procedural memories from semantic memories.
Extract reusable patterns, procedures, and lessons from the following semantic memories.
Requirements:
- Describe in the format of "what to do and how to succeed"
- Abstract concrete contexts into procedures
- Make it useful for future decision-making and actions
Output: Extracted patterns, procedures, and lesson text only (no explanation)"""

L3_TO_L4_SYSTEM = """You are an AI that generates meta-memories (self-model) from procedural memories.
Extract high-level identity, evolution history, and values from the following procedural memories.
Requirements:
- Express "who this agent is", "what it excels at", "how it has grown"
- Increase abstraction level, preserving only essential patterns
Output: Meta-memory text only (no explanation)"""

RERANK_SYSTEM = """You are an AI that reranks search results by relevance.
You are given a query and a list of candidate memories.
List the candidate index numbers in order of relevance to the query.
Output format: JSON array (index numbers only) e.g.: [2, 0, 3, 1]"""


class MemoryLLM:
    """
    LLM client supporting both OpenClaw (llm_client.py) and Anthropic SDK
    Provider auto-detection: auth-profiles.json -> ANTHROPIC_API_KEY -> error
    """

    def __init__(self, extract_model: str = EXTRACT_MODEL, compress_model: str = COMPRESS_MODEL):
        self.extract_model = extract_model
        self.compress_model = compress_model
        self._api_key = _get_anthropic_key()
        if not self._api_key:
            raise RuntimeError(
                "LLM API key not found.\n"
                "Set the ANTHROPIC_API_KEY environment variable or\n"
                "configure ~/.openclaw/agents/main/agent/auth-profiles.json."
            )

    def _call(self, prompt: str, system: str, model: str, max_tokens: int = 2048, temperature: float = 0.2) -> str:
        """Invoke LLM (Anthropic SDK)"""
        return _call_anthropic(prompt, system, model, max_tokens, temperature)

    def extract(self, session_text: str) -> list:
        """Generate L1 entries from conversation text. Returns a JSON array."""
        try:
            result = self._call(
                prompt=f"Extract memory entries from the following conversation:\n\n{session_text}",
                system=EXTRACT_SYSTEM,
                model=self.extract_model,
                max_tokens=2048,
            )
            # Parse JSON
            result = result.strip()
            # Remove code blocks if present
            if result.startswith("```"):
                lines = result.split("\n")
                result = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            extracted = json.loads(result)
            if not isinstance(extracted, list):
                return []
            # Filter by importance (>= 0.7)
            return [e for e in extracted if isinstance(e, dict) and e.get("importance", 0) >= 0.7]
        except Exception as e:
            print(f"[MemoryLLM] extract error: {e}", file=sys.stderr)
            return []

    def compress(self, memories, target_layer: int) -> str:
        """
        Accepts list[Memory] and returns compressed text.
        target_layer: destination layer number
        """
        content_list = "\n".join(
            f"[{i+1}] (importance:{m.importance:.1f}) {m.content}"
            for i, m in enumerate(memories)
        )
        prompt = f"Compress the following {len(memories)} memories:\n\n{content_list}"

        if target_layer == 2:
            system = L1_TO_L2_SYSTEM
        elif target_layer == 3:
            system = L2_TO_L3_SYSTEM
        elif target_layer == 4:
            system = L3_TO_L4_SYSTEM
        else:
            system = L1_TO_L2_SYSTEM

        try:
            return self._call(
                prompt=prompt,
                system=system,
                model=self.compress_model,
                max_tokens=1024,
            )
        except Exception as e:
            print(f"[MemoryLLM] compress error: {e}", file=sys.stderr)
            return ""

    def rerank(self, query: str, candidates) -> list:
        """
        Rerank candidate memories against a query.
        candidates: list[Memory]
        Returns: reranked list[Memory]
        """
        if not candidates:
            return candidates

        candidate_text = "\n".join(
            f"[{i}] {m.content[:200]}" for i, m in enumerate(candidates)
        )
        prompt = f"Query: {query}\n\nCandidate memories:\n{candidate_text}"

        try:
            result = self._call(
                prompt=prompt,
                system=RERANK_SYSTEM,
                model=self.extract_model,
                max_tokens=256,
            ).strip()
            if result.startswith("```"):
                lines = result.split("\n")
                result = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            indices = json.loads(result)
            reranked = []
            seen = set()
            for idx in indices:
                if isinstance(idx, int) and 0 <= idx < len(candidates) and idx not in seen:
                    reranked.append(candidates[idx])
                    seen.add(idx)
            # Append any remaining candidates not yet included
            for i, m in enumerate(candidates):
                if i not in seen:
                    reranked.append(m)
            return reranked
        except Exception as e:
            print(f"[MemoryLLM] rerank error: {e}", file=sys.stderr)
            return candidates
