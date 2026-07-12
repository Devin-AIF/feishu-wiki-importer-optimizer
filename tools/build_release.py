#!/usr/bin/env python3
"""Build a minimal, allowlisted Skill release archive.

This intentionally never packages the repository root.  It copies only files
that belong to the installable Skill, scans the result for common accidental
secrets/private-data markers, and then writes a ZIP archive.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "feishu-wiki-importer-optimizer"
SOURCE = ROOT / "skill" / SKILL_NAME
DEFAULT_OUTPUT = ROOT / "outputs"

ALLOWED_PATHS = (
    Path("SKILL.md"),
    Path("agents/openai.yaml"),
    Path("scripts/common.py"),
    Path("scripts/feishu_wiki.py"),
    Path("scripts/feishu_wiki/__init__.py"),
    Path("scripts/feishu_wiki/cli.py"),
    Path("scripts/feishu_wiki/lark_client.py"),
    Path("scripts/feishu_wiki/paths.py"),
    Path("scripts/feishu_wiki/prepare.py"),
    Path("scripts/feishu_wiki/push.py"),
    Path("scripts/feishu_wiki/service.py"),
    Path("scripts/feishu_wiki/storage.py"),
    Path("scripts/feishu_wiki/transforms.py"),
    Path("scripts/feishu_wiki/whiteboards.py"),
    Path("scripts/feishu_wiki/writer.py"),
    Path("scripts/feishu_doc_tools.py"),
    Path("scripts/feishu_prepare_chapters.py"),
    Path("scripts/feishu_push_chapters.py"),
    Path("scripts/init_project.py"),
    Path("scripts/requirements.txt"),
    Path("scripts/setup.sh"),
    Path("scripts/doctor.sh"),
    Path("references/runtime-data.md"),
    Path("references/project-layout.md"),
    Path("references/workspace.schema.json"),
    Path("references/project.schema.json"),
    Path("references/outline.schema.json"),
    Path("references/remote-nodes.schema.json"),
    Path("assets/chapters_nodes.example.json"),
    Path("assets/mermaid_maps.example.json"),
    Path("assets/workspace.template.json"),
    Path("assets/project.template.json"),
    Path("assets/outline.template.json"),
    Path("assets/remote_nodes.template.json"),
    Path("assets/mermaid_maps.template.json"),
    Path("assets/uploaded_images.template.json"),
)

FORBIDDEN_PARTS = {
    ".git", ".venv", "__pycache__", "chapters", "scratch", "runtime_backups",
    "backups", "temp_images", "archive", "verification", "private-workspace",
}
FORBIDDEN_NAMES = {
    "verify_push.py", "uploaded_images.json", "chapters_nodes.json", "mermaid_maps.json",
}
SENSITIVE_PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "openai-key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "aws-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "absolute-user-path": re.compile(r"(?:^|[\"'])/Users/[^/]+/|(?:^|[\"'])/home/[^/]+/"),
}
SAFE_JSON_SUFFIXES = (".example.json", ".template.json", ".schema.json")


def copy_allowlist(stage: Path) -> list[Path]:
    copied: list[Path] = []
    for relative in ALLOWED_PATHS:
        source = SOURCE / relative
        if not source.is_file():
            raise FileNotFoundError(f"Required release file missing: {source}")
        destination = stage / SKILL_NAME / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(destination)
    return copied


def scan_stage(stage: Path) -> list[str]:
    problems: list[str] = []
    files = [p for p in stage.rglob("*") if p.is_file()]
    allowed_relative = {Path(SKILL_NAME) / path for path in ALLOWED_PATHS}
    actual_relative = {path.relative_to(stage) for path in files}
    unexpected = sorted(actual_relative - allowed_relative)
    if unexpected:
        problems.extend(f"unexpected release file: {p}" for p in unexpected)

    for path in files:
        relative = path.relative_to(stage)
        if any(part in FORBIDDEN_PARTS for part in relative.parts):
            problems.append(f"forbidden directory in release: {relative}")
        if path.name in FORBIDDEN_NAMES:
            problems.append(f"forbidden filename in release: {relative}")
        if path.suffix == ".json" and not path.name.endswith(SAFE_JSON_SUFFIXES):
            problems.append(f"non-example JSON in release: {relative}")
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in SENSITIVE_PATTERNS.items():
            if pattern.search(text) or pattern.search(str(relative)):
                problems.append(f"{label} detected in {relative}")
    return problems


def zip_stage(stage: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(stage))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an allowlisted Skill release ZIP")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)

    output_dir = args.output_dir.resolve()
    stage = output_dir / f".{SKILL_NAME}.stage"
    if stage.exists():
        shutil.rmtree(stage)
    try:
        copied = copy_allowlist(stage)
        problems = scan_stage(stage)
        if problems:
            print("RELEASE BLOCKED:", file=sys.stderr)
            print("\n".join(f"- {item}" for item in problems), file=sys.stderr)
            return 2
        print(f"Allowlist scan passed: {len(copied)} files")
        if args.check_only:
            return 0
        output_dir.mkdir(parents=True, exist_ok=True)
        destination = output_dir / f"{SKILL_NAME}.zip"
        zip_stage(stage, destination)
        print(f"Release archive: {destination}")
        return 0
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == "__main__":
    raise SystemExit(main())
