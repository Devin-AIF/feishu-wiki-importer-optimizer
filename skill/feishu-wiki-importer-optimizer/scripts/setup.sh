#!/usr/bin/env bash
# Bootstrap an isolated virtualenv and install the required third-party dependencies.
# 同时提示检查飞书 CLI (lark-cli) 是否就绪 —— lark-cli 是系统级工具，不通过 pip 安装。
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DEFAULT_WORKSPACE="$HOME/.local/state/feishu-wiki-importer-optimizer"
if [ -d "${REPO_ROOT}.private-workspace" ]; then
  DEFAULT_WORKSPACE="${REPO_ROOT}.private-workspace"
fi
WORKSPACE="${FEISHU_WIKI_WORKSPACE:-$DEFAULT_WORKSPACE}"
VENV="$WORKSPACE/.venv"

echo "== [1/2] 创建私有运行目录与隔离 venv =="
if [ ! -f "$WORKSPACE/workspace.json" ]; then
  python3 "$SCRIPT_DIR/init_project.py" --workspace "$WORKSPACE" --project default
else
  PROJECT=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["default_project"])' "$WORKSPACE/workspace.json")
  if [ ! -f "$WORKSPACE/projects/$PROJECT/project.json" ]; then
    python3 "$SCRIPT_DIR/init_project.py" --workspace "$WORKSPACE"
  fi
fi
chmod 700 "$WORKSPACE" 2>/dev/null || true
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
echo "  私有分层工作区：$WORKSPACE"
echo "  Done. 激活：source '$VENV/bin/activate'"

echo
echo "== [2/2] 检查飞书 CLI (lark-cli) =="
if command -v lark-cli >/dev/null 2>&1; then
  echo "  lark-cli 已安装 ($(lark-cli --version 2>/dev/null | head -1))"
  if lark-cli whoami >/dev/null 2>&1; then
    echo "  lark-cli 已登录 ✅"
  else
    echo "  ⚠️  lark-cli 尚未登录，请执行：lark-cli auth login"
  fi
else
  echo "  ⚠️  未检测到 lark-cli。本工具依赖它读写飞书文档，请先安装并登录："
  echo "        brew install lark-cli"
  echo "        lark-cli auth login"
fi

echo
echo "全部就绪后可运行：bash '$SCRIPT_DIR/doctor.sh'  做最终体检。"
