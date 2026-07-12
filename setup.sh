#!/usr/bin/env bash
# 已弃用的兼容入口：环境和运行数据均由 Skill 脚本管理。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "[DEPRECATED] 根目录 setup.sh 将在迁移完成后删除；请使用 Skill scripts/setup.sh。" >&2
exec bash "$ROOT/skill/feishu-wiki-importer-optimizer/scripts/setup.sh" "$@"
