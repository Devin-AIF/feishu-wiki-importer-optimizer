#!/usr/bin/env bash
# doctor.sh — 一键环境体检：检查本工具箱运行所需的全部前置依赖。
# 用法：bash doctor.sh
# 任何一项 FAIL 都会给出修复命令；全部 PASS 即可以开始使用。
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DEFAULT_WORKSPACE="$HOME/.local/state/feishu-wiki-importer-optimizer"
if [ -d "${REPO_ROOT}.private-workspace" ]; then
  DEFAULT_WORKSPACE="${REPO_ROOT}.private-workspace"
fi
WORKSPACE="${FEISHU_WIKI_WORKSPACE:-$DEFAULT_WORKSPACE}"
VENV="$WORKSPACE/.venv"
PASS=0
FAIL=0

ok()   { echo "  [PASS] $1"; PASS=$((PASS+1)); }
bad()  { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

echo "=================================================="
echo "  飞书知识库文档工具 · 环境体检 (doctor)"
echo "  目录: $SCRIPT_DIR"
echo "  私有运行目录: $WORKSPACE"
echo "=================================================="

# 1) Python 3.8+
echo "-- Python --"
if command -v python3 >/dev/null 2>&1; then
  ver=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)
  major=$(echo "$ver" | cut -d. -f1)
  minor=$(echo "$ver" | cut -d. -f2)
  if [ "$major" -gt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -ge 8 ]; }; then
    ok "python3 版本 $ver (要求 >= 3.8)"
  else
    bad "python3 版本 $ver 过低，请升级到 3.8+"
  fi
else
  bad "未找到 python3，请先安装 Python 3.8+"
fi

# 2) lark-cli
echo "-- 飞书 CLI (lark-cli) --"
if command -v lark-cli >/dev/null 2>&1; then
  lv=$(lark-cli --version 2>/dev/null | head -1)
  ok "lark-cli 已安装 ($lv)"
  # 2a) 登录态检查
  if lark-cli whoami >/dev/null 2>&1; then
    prof=$(lark-cli whoami 2>/dev/null | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("profile","?"))' 2>/dev/null)
    ok "lark-cli 已登录 (profile: ${prof:-unknown})"
  else
    bad "lark-cli 未登录 → 执行: lark-cli auth login"
  fi
else
  bad "未找到 lark-cli → 安装: brew install lark-cli  (装完执行 lark-cli auth login)"
fi

# 3) Python 依赖（在 .venv 或当前 python 中可用其一即可）
echo "-- Python 依赖 beautifulsoup4 / Pillow --"
if [ -d "$VENV" ]; then
  if "$VENV/bin/python" -c 'import bs4; import PIL' >/dev/null 2>&1; then
    ok "beautifulsoup4 / Pillow 已在私有 venv 安装"
  else
    bad "beautifulsoup4 或 Pillow 缺失 → 执行: bash '$SCRIPT_DIR/setup.sh'"
  fi
elif python3 -c 'import bs4; import PIL' >/dev/null 2>&1; then
  ok "beautifulsoup4 / Pillow 已在当前 python 可用"
else
  bad "beautifulsoup4 或 Pillow 缺失 → 执行: bash '$SCRIPT_DIR/setup.sh'  (或 pip install -r requirements.txt)"
fi

# 4) 发布代码文件与私有运行目录齐备
echo "-- 发布代码文件 --"
for f in feishu_wiki.py feishu_wiki/cli.py feishu_wiki/writer.py requirements.txt; do
  if [ -f "$SCRIPT_DIR/$f" ]; then
    ok "存在 $f"
  else
    bad "缺失 $f （仓库不完整，请重新下载）"
  fi
done

echo "-- 私有运行文件 --"
for f in mappings/chapters_nodes.json mappings/mermaid_maps.json; do
  if [ -f "$WORKSPACE/$f" ]; then
    ok "存在 $f"
  else
    bad "缺失 $WORKSPACE/$f （请从受控私有备份复制，或在命令中显式传入 --mapping / --maps）"
  fi
done

echo "=================================================="
echo "  结果: $PASS PASS / $FAIL FAIL"
if [ "$FAIL" -eq 0 ]; then
  echo "  全部就绪 ✅ 可直接开始《标准工作流》。"
else
  echo "  请先修复上方 [FAIL] 项再继续。"
fi
echo "=================================================="
exit $FAIL
