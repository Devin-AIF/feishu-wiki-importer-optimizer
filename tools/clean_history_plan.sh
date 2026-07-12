#!/usr/bin/env bash
# Generate a clean, local-only copy of the Git history.
# This script NEVER changes origin and NEVER pushes. Review the result first.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT="${1:-$ROOT/../feishu-wiki-importer-optimizer-clean-history}"

if ! command -v git-filter-repo >/dev/null 2>&1; then
  echo "git-filter-repo is required. Install it first (for example: brew install git-filter-repo)." >&2
  exit 2
fi
if [ -e "$OUTPUT" ]; then
  echo "Refusing to overwrite existing output: $OUTPUT" >&2
  exit 2
fi

git clone --no-local "$ROOT" "$OUTPUT"
cd "$OUTPUT"

# Remove historical operational data and prior layout. The current refactored
# source tree will remain; review it before deciding whether to publish it.
git filter-repo --force \
  --path chapters_nodes.json \
  --path mermaid_maps.json \
  --path archive/ \
  --path-glob 'chapters_nodes*.json' \
  --path-glob 'mermaid_maps*.json' \
  --invert-paths

echo
echo "Local clean-history copy prepared: $OUTPUT"
echo "No remote was pushed or changed. Run the checks below before any remote action:"
echo "  cd '$OUTPUT'"
echo "  git log --all --oneline"
echo "  git log --all -S 'node_token' --all --stat"
echo "  python3 tools/check_release.py"
echo
echo "After manual approval, add a new remote and force-push explicitly. Do not reuse this script to push."
