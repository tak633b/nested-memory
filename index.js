/**
 * Nested Memory Plugin for OpenClaw
 *
 * 4層ネステッドメモリシステム
 * - before_agent_start: 関連L1-L3をクエリして上位コンテキストに注入
 * - agent_end: 会話からL1エントリを自動抽出・保存
 *
 * 圧縮スケジュール (launchd 管理):
 * - 毎日 3:00 AM: python3 cli.py compress --layer 1  (L1→L2)
 * - 毎週月曜 3:30 AM: python3 cli.py compress --layer 2  (L2→L3)
 * → install.sh を実行して launchd plist を登録してください
 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";
import os from "node:os";

const execFileAsync = promisify(execFile);

const EXT_DIR = path.resolve(
  process.env.HOME || os.homedir(),
  ".openclaw/extensions/nested-memory"
);

const CLI_PATH = path.join(EXT_DIR, "cli.py");

/**
 * CLIコマンドを実行
 */
async function runCLI(args = [], timeoutMs = 30000) {
  try {
    const { stdout, stderr } = await execFileAsync(
      "python3",
      [CLI_PATH, ...args],
      {
        timeout: timeoutMs,
        env: { ...process.env },
        cwd: EXT_DIR,
      }
    );
    return { ok: true, stdout: stdout.trim(), stderr: stderr.trim() };
  } catch (err) {
    return {
      ok: false,
      error: String(err.message || err),
      stdout: err.stdout || "",
      stderr: err.stderr || "",
    };
  }
}

/**
 * メッセージからテキストを抽出
 */
function extractTexts(messages) {
  const texts = [];
  if (!messages || !Array.isArray(messages)) return texts;

  for (const msg of messages) {
    if (!msg || typeof msg !== "object") continue;
    const { role, content } = msg;
    if (role !== "user" && role !== "assistant") continue;

    if (typeof content === "string") {
      texts.push({ role, text: content });
    } else if (Array.isArray(content)) {
      for (const block of content) {
        if (block?.type === "text" && typeof block.text === "string") {
          texts.push({ role, text: block.text });
        }
      }
    }
  }
  return texts;
}

const nestedMemoryPlugin = {
  id: "nested-memory",
  name: "Nested Memory",
  description: "4-layer nested memory: Episodic→Semantic→Procedural→Meta",
  kind: "memory",

  register(api) {
    const cfg = api.pluginConfig || {};
    const autoRecall = cfg.autoRecall !== false;
    const autoCapture = cfg.autoCapture !== false;

    api.logger.info(
      `nested-memory: registered (recall=${autoRecall}, capture=${autoCapture})`
    );

    // ======================================================================
    // Auto-Recall: セッション開始時に関連メモリをコンテキストに注入
    // ======================================================================
    if (autoRecall) {
      api.on("before_agent_start", async (event) => {
        let prompt = event.prompt;
        if (!prompt || prompt.length < 5) return;
        if (prompt.includes("HEARTBEAT") || prompt === "NO_REPLY") return;

        // システム注入メタデータを除去してクエリ抽出
        prompt = prompt.replace(/\[.*?\]/g, "").trim().slice(0, 200);
        if (!prompt) return;

        const result = await runCLI(["search", prompt, "--limit", "5"], 15000);
        if (!result.ok || !result.stdout) return;

        // 検索結果があればコンテキストに注入
        if (result.stdout.includes("Found") && !result.stdout.includes("Found 0")) {
          const injection = `\n## Nested Memory (関連記憶)\n${result.stdout}\n`;
          if (event.context) {
            event.context += injection;
          } else {
            event.context = injection;
          }
          api.logger.debug(`nested-memory: injected recall for query: ${prompt.slice(0, 50)}`);
        }
      });
    }

    // ======================================================================
    // Auto-Capture: セッション終了時にL1記憶を自動抽出
    // ======================================================================
    if (autoCapture) {
      api.on("agent_end", async (event) => {
        const messages = event.messages || [];
        if (messages.length < 2) return;

        const texts = extractTexts(messages);
        if (texts.length < 1) return;

        // 最新の会話テキストを結合（最大3000文字）
        const combined = texts
          .slice(-6)
          .map((t) => `[${t.role}] ${t.text}`)
          .join("\n")
          .slice(0, 3000);

        if (combined.length < 50) return;

        const result = await runCLI(["extract", combined], 60000);
        if (!result.ok) {
          api.logger.warn(`nested-memory: capture failed: ${result.error}`);
          return;
        }

        if (result.stdout) {
          api.logger.info(`nested-memory: auto-captured: ${result.stdout.slice(0, 100)}`);
        }
      });
    }

    // NOTE: daily/weekly compression is handled by launchd plists (installed via install.sh)
    // See: com.baltech.nested-memory.daily.plist  — runs `python3 cli.py compress --layer 1` at 3:00 AM daily
    //      com.baltech.nested-memory.weekly.plist — runs `python3 cli.py compress --layer 2` at 3:30 AM every Monday
  },
};

export default nestedMemoryPlugin;
