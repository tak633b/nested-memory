#!/usr/bin/env zsh
# install.sh — nested-memory セットアップスクリプト
# Usage: ./install.sh
# 実行内容:
#   1. extensions/ への配置確認
#   2. DB スキーマ初期化
#   3. launchd plist 配置 & ロード

set -euo pipefail

SCRIPT_DIR="${0:A:h}"
EXT_DIR="${HOME}/.openclaw/extensions/nested-memory"
LAUNCH_AGENTS="${HOME}/Library/LaunchAgents"
LOG_DIR="${HOME}/.openclaw/logs"

DAILY_PLIST="com.baltech.nested-memory.daily.plist"
WEEKLY_PLIST="com.baltech.nested-memory.weekly.plist"

echo "=== nested-memory インストール開始 ==="

# ── 1. extensions/ への配置 ────────────────────────────────────────────────
echo "[1/4] extensions ディレクトリの確認..."
if [[ "${SCRIPT_DIR}" != "${EXT_DIR}" ]]; then
  echo "  → ${EXT_DIR} にコピーします"
  mkdir -p "${EXT_DIR}"
  cp -R "${SCRIPT_DIR}/." "${EXT_DIR}/"
  echo "  ✓ コピー完了"
else
  echo "  ✓ すでに正しいディレクトリです"
fi

# ── 2. ログディレクトリ作成 ────────────────────────────────────────────────
echo "[2/4] ログディレクトリを作成..."
mkdir -p "${LOG_DIR}"
echo "  ✓ ${LOG_DIR}"

# ── 3. DB スキーマ初期化 ───────────────────────────────────────────────────
echo "[3/4] DB スキーマを初期化..."
/usr/bin/env python3 "${EXT_DIR}/nested_memory/store.py" --init
echo "  ✓ DB 初期化完了"

# ── 4. launchd plist 配置 & ロード ────────────────────────────────────────
echo "[4/4] launchd plist を配置..."
mkdir -p "${LAUNCH_AGENTS}"

for PLIST in "${DAILY_PLIST}" "${WEEKLY_PLIST}"; do
  SRC="${EXT_DIR}/${PLIST}"
  DST="${LAUNCH_AGENTS}/${PLIST}"

  if [[ ! -f "${SRC}" ]]; then
    echo "  ✗ plist が見つかりません: ${SRC}"
    exit 1
  fi

  # 既にロード済みなら先に unload
  if launchctl list | grep -q "${PLIST%.plist}" 2>/dev/null; then
    echo "  → 既存 plist をアンロード: ${PLIST}"
    launchctl unload "${DST}" 2>/dev/null || true
  fi

  cp "${SRC}" "${DST}"
  launchctl load "${DST}"
  echo "  ✓ ロード完了: ${PLIST}"
done

echo ""
echo "=== インストール完了 ==="
echo ""
echo "登録されたジョブ:"
echo "  com.baltech.nested-memory.daily  — 毎日 03:00 に L1→L2 圧縮"
echo "  com.baltech.nested-memory.weekly — 毎週月曜 03:30 に L2→L3 圧縮"
echo ""
echo "ログ出力先:"
echo "  ${LOG_DIR}/nested-memory-daily.log"
echo "  ${LOG_DIR}/nested-memory-weekly.log"
echo ""
echo "手動実行テスト:"
echo "  launchctl start com.baltech.nested-memory.daily"
echo "  launchctl start com.baltech.nested-memory.weekly"
