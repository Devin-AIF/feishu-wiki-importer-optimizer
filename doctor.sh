#!/usr/bin/env bash
# 兼容入口：环境和运行数据均由 Skill 脚本管理。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$ROOT/skill/feishu-wiki-importer-optimizer/scripts/doctor.sh" "$@"
