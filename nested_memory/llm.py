"""
llm.py — LLM抽象レイヤー
Anthropic SDK直叩き + OpenClaw llm_client.py 両対応
プロバイダー自動検出ロジック付き
"""
import os
import json
import sys

EXTRACT_MODEL = "claude-haiku-4-5"
COMPRESS_MODEL = "claude-sonnet-4-6"


def _get_anthropic_key() -> str:
    """APIキー取得: OpenClaw auth-profiles.json（最優先）→ ANTHROPIC_API_KEY 環境変数（フォールバック）
    task#92: OpenClawのキーを最優先にする（scripts/llm_client.py の実装パターンに準拠）
    """
    # 1. OpenClaw auth-profiles.json（最優先）
    # main agentのプロファイルを最初に試みる
    for agent_name in ("main", "mini-bal"):
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

    # 2. ANTHROPIC_API_KEY 環境変数（フォールバック）
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
    """Anthropic SDK直叩き"""
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


# --- プロンプト定義 ---

EXTRACT_SYSTEM = """あなたは会話から重要な記憶エントリを抽出するAIです。
以下の会話テキストから、記憶に値するエントリを抽出してください。
抽出基準:
- 決定事項（何かが決まった、承認された）
- 固有名詞（人名、プロジェクト名、ツール名）
- 数値データ（金額、日付、割合）
- タスク・行動項目
- 感情的に重要な出来事
- 手順・方法の発見

出力形式: JSON配列のみ。説明文は不要。
[{"content": "記憶内容（1-2文）", "tags": ["tag1", "tag2"], "importance": 0.0-1.0}]
重要度0.7以上のみ抽出してください（ノイズ除去）。"""

L1_TO_L2_SYSTEM = """あなたはエピソード記憶を意味記憶に圧縮するAIです。
以下のエピソード記憶（会話の断片）を、意味的に統合・圧縮してください。
要件:
- 具体的な固有名詞・数値・日付は必ず保持すること
- 重複・冗長な情報を除去すること
- 1つの統合されたセマンティック記憶として出力すること
- 日本語で出力すること
出力: 圧縮された記憶テキストのみ（説明なし）"""

L2_TO_L3_SYSTEM = """あなたはセマンティック記憶から手続き記憶を抽出するAIです。
以下のセマンティック記憶から、再利用可能なパターン・手順・教訓を抽出してください。
要件:
- 「何をどうすればうまくいくか」という形式で記述
- 具体的なコンテキストを抽象化して手順化すること
- 将来の意思決定や行動に役立つ形で
- 日本語で出力すること
出力: 抽出されたパターン・手順・教訓テキストのみ（説明なし）"""

L3_TO_L4_SYSTEM = """あなたは手続き記憶からメタ記憶（自己モデル）を生成するAIです。
以下の手続き記憶から、高レベルなアイデンティティ・進化履歴・価値観を抽出してください。
要件:
- このエージェントが「何者か」「何が得意か」「どう成長してきたか」を表現する
- 抽象度を上げ、本質的なパターンのみを残す
- 日本語で出力すること
出力: メタ記憶テキストのみ（説明なし）"""

RERANK_SYSTEM = """あなたは検索結果を関連度でリランクするAIです。
クエリと候補記憶のリストが与えられます。
クエリとの関連度が高い順に候補のインデックス番号を並べてください。
出力形式: JSON配列（インデックス番号のみ）例: [2, 0, 3, 1]"""


class MemoryLLM:
    """
    OpenClaw (llm_client.py) / Anthropic SDK 両対応LLMクライアント
    プロバイダー自動検出: ANTHROPIC_API_KEY → auth-profiles.json → エラー
    """

    def __init__(self, extract_model: str = EXTRACT_MODEL, compress_model: str = COMPRESS_MODEL):
        self.extract_model = extract_model
        self.compress_model = compress_model
        self._api_key = _get_anthropic_key()
        if not self._api_key:
            raise RuntimeError(
                "LLM APIキーが見つかりません。\n"
                "ANTHROPIC_API_KEY 環境変数を設定するか、\n"
                "~/.openclaw/agents/mini-bal/agent/auth-profiles.json を確認してください。"
            )

    def _call(self, prompt: str, system: str, model: str, max_tokens: int = 2048, temperature: float = 0.2) -> str:
        """LLM呼び出し（Anthropic SDK）"""
        return _call_anthropic(prompt, system, model, max_tokens, temperature)

    def extract(self, session_text: str) -> list:
        """会話テキストからL1エントリを生成。JSON配列を返す"""
        try:
            result = self._call(
                prompt=f"以下の会話から記憶エントリを抽出してください:\n\n{session_text}",
                system=EXTRACT_SYSTEM,
                model=self.extract_model,
                max_tokens=2048,
            )
            # JSONパース
            result = result.strip()
            # コードブロックの除去
            if result.startswith("```"):
                lines = result.split("\n")
                result = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            extracted = json.loads(result)
            if not isinstance(extracted, list):
                return []
            # 重要度フィルタ（0.7以上）
            return [e for e in extracted if isinstance(e, dict) and e.get("importance", 0) >= 0.7]
        except Exception as e:
            print(f"[MemoryLLM] extract error: {e}", file=sys.stderr)
            return []

    def compress(self, memories, target_layer: int) -> str:
        """
        memories: list[Memory] を受け取り、圧縮テキストを返す
        target_layer: 圧縮先の層番号
        """
        content_list = "\n".join(
            f"[{i+1}] (重要度:{m.importance:.1f}) {m.content}"
            for i, m in enumerate(memories)
        )
        prompt = f"以下の{len(memories)}件の記憶を圧縮してください:\n\n{content_list}"

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
        クエリに対して候補記憶をリランク。
        candidates: list[Memory]
        返値: リランク済みlist[Memory]
        """
        if not candidates:
            return candidates

        candidate_text = "\n".join(
            f"[{i}] {m.content[:200]}" for i, m in enumerate(candidates)
        )
        prompt = f"クエリ: {query}\n\n候補記憶:\n{candidate_text}"

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
            # 残ったものを末尾に追加
            for i, m in enumerate(candidates):
                if i not in seen:
                    reranked.append(m)
            return reranked
        except Exception as e:
            print(f"[MemoryLLM] rerank error: {e}", file=sys.stderr)
            return candidates
