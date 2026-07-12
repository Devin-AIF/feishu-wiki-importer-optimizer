#!/usr/bin/env python3
"""离线初始化飞书知识库导入项目的私有工作区。

本脚本只创建本地目录和合成配置，不导入 common.py、不调用
lark-cli、不访问网络，也不猜测任何云端资源标识。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SCRIPT_DIR.parents[2]
ASSETS_DIR = SKILL_DIR / "assets"
PROJECT_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")

PROJECT_DIRECTORIES = (
    "source/chapters",
    "source/images",
    "config",
    "generated/prepared",
    "state",
    "previews",
    "backups/runtime",
    "cache",
    "logs",
)

PROJECT_TEMPLATE_TARGETS = (
    ("project.template.json", "project.json"),
    ("outline.template.json", "config/outline.json"),
    ("mermaid_maps.template.json", "generated/mermaid_maps.json"),
    ("remote_nodes.template.json", "state/remote_nodes.json"),
    ("uploaded_images.template.json", "state/uploaded_images.json"),
)


class InitProjectError(RuntimeError):
    """安全预检失败；调用方应在写入任何骨架文件前中止。"""


def _is_within(path: Path, parent: Path) -> bool:
    """返回 path 是否等于 parent 或位于 parent 内。"""
    return path == parent or parent in path.parents


def _default_workspace() -> Path:
    migrated = Path(f"{REPO_ROOT}.private-workspace")
    if migrated.is_dir():
        return migrated.resolve()
    state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    if state_home:
        base = Path(state_home).expanduser()
    else:
        base = Path.home() / ".local" / "state"
    return (base / "feishu-wiki-importer-optimizer").resolve()


def resolve_workspace(explicit: Optional[str]) -> Path:
    """按 CLI > 环境变量 > 安全默认值解析工作区。"""
    raw = explicit or os.environ.get("FEISHU_WIKI_WORKSPACE", "").strip()
    workspace = Path(raw).expanduser().resolve() if raw else _default_workspace()
    home = Path.home().resolve()
    if workspace == Path(workspace.anchor) or workspace == home:
        raise InitProjectError("拒绝将根目录或用户 HOME 作为工作区")
    if _is_within(workspace, SKILL_DIR):
        raise InitProjectError("工作区不得位于可发布 Skill 目录内")
    if (REPO_ROOT / ".git").exists() and _is_within(workspace, REPO_ROOT):
        raise InitProjectError("工作区不得位于开发仓库内")
    return workspace


def validate_project_slug(value: str) -> str:
    slug = str(value or "")
    if not PROJECT_SLUG_RE.fullmatch(slug):
        raise InitProjectError(
            "项目名必须是 1-64 位小写字母、数字或连字符，"
            "且不能以连字符开头/结尾"
        )
    return slug


def _load_json(path: Path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise InitProjectError(f"无法读取 JSON: {path}: {exc}") from exc


def _load_template(name: str):
    path = ASSETS_DIR / name
    data = _load_json(path)
    if not isinstance(data, dict):
        raise InitProjectError(f"模板顶层必须是 object: {path}")
    return data


def _preload_templates() -> Dict[str, dict]:
    names = ["workspace.template.json"] + [name for name, _ in PROJECT_TEMPLATE_TARGETS]
    return {name: _load_template(name) for name in names}


def _existing_workspace_config(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    data = _load_json(path)
    if not isinstance(data, dict):
        raise InitProjectError(f"workspace.json 必须是 JSON object: {path}")
    default_project = data.get("default_project")
    validate_project_slug(default_project)
    return data


def _atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp_name = tempfile.mkstemp(prefix=".init-project-", suffix=".json", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        path.chmod(0o600)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _secure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def _backup_existing(workspace: Path, paths: List[Path]) -> Optional[Path]:
    existing = [path for path in paths if path.is_file()]
    if not existing:
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_root = workspace / "archives" / "init-project" / stamp
    _secure_directory(backup_root)
    for source in existing:
        relative = source.relative_to(workspace)
        destination = backup_root / relative
        _secure_directory(destination.parent)
        shutil.copy2(source, destination)
        destination.chmod(0o600)
    return backup_root


def _build_documents(
    workspace_config: Optional[dict], project: str, templates: Dict[str, dict]
) -> Dict[str, object]:
    if workspace_config is None:
        workspace_data = dict(templates["workspace.template.json"])
        workspace_data["default_project"] = project
    else:
        workspace_data = dict(workspace_config)

    project_data = dict(templates["project.template.json"])
    project_data["project_id"] = project
    project_data["display_name"] = project

    return {
        "workspace.json": workspace_data,
        "project.json": project_data,
        "config/outline.json": templates["outline.template.json"],
        "generated/mermaid_maps.json": templates["mermaid_maps.template.json"],
        "state/remote_nodes.json": templates["remote_nodes.template.json"],
        "state/uploaded_images.json": templates["uploaded_images.template.json"],
    }


def initialize(
    workspace: Path, project: Optional[str], force: bool = False
) -> Tuple[Path, Optional[Path]]:
    """创建项目骨架，返回 (项目目录, 备份目录)。"""
    workspace_config_path = workspace / "workspace.json"
    workspace_config = _existing_workspace_config(workspace_config_path)
    templates = _preload_templates()
    selected = validate_project_slug(
        project or (workspace_config or {}).get("default_project") or "default"
    )
    project_dir = workspace / "projects" / selected
    documents = _build_documents(workspace_config, selected, templates)

    targets = {workspace_config_path: documents["workspace.json"]}
    for relative, data in documents.items():
        if relative == "workspace.json":
            continue
        targets[project_dir / relative] = data

    project_targets = [path for path in targets if path != workspace_config_path]
    invalid_targets = [path for path in targets if path.exists() and not path.is_file()]
    if invalid_targets:
        rendered = "\n  - ".join(str(path) for path in invalid_targets)
        raise InitProjectError(f"骨架文件目标被非文件占用：\n  - {rendered}")
    existing_project_targets = [path for path in project_targets if path.exists()]
    if existing_project_targets and not force:
        rendered = "\n  - ".join(str(path) for path in existing_project_targets)
        raise InitProjectError(
            "项目已包含骨架文件，未做任何修改。"
            f"如需重建请显式使用 --force：\n  - {rendered}"
        )

    # 所有模板与目标均在此前完成预检；之后才开始创建目录。
    _secure_directory(workspace)
    _secure_directory(workspace / "archives")
    _secure_directory(workspace / "projects")
    _secure_directory(project_dir)
    for relative in PROJECT_DIRECTORIES:
        _secure_directory(project_dir / relative)

    backup_candidates = list(project_targets)
    if force and workspace_config_path.exists():
        backup_candidates.append(workspace_config_path)
    backup_root = _backup_existing(workspace, backup_candidates) if force else None

    newly_created: List[Path] = []
    try:
        for path, data in targets.items():
            if path == workspace_config_path and path.exists() and not force:
                path.chmod(0o600)
                continue
            existed = path.exists()
            _atomic_write_json(path, data)
            if not existed:
                newly_created.append(path)
    except Exception:
        # 只回滚本次新建的已知文件；既有文件由 force 备份保护。
        for path in reversed(newly_created):
            try:
                path.unlink()
            except OSError:
                pass
        raise

    return project_dir, backup_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="创建私有工作区的分层项目骨架（完全离线）")
    parser.add_argument("--workspace", help="私有工作区路径")
    parser.add_argument("--project", help="项目 slug（默认读 workspace.json，再回落 default）")
    parser.add_argument("--force", action="store_true", help="备份后重建已知骨架文件")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        workspace = resolve_workspace(args.workspace)
        project_dir, backup_root = initialize(workspace, args.project, args.force)
    except InitProjectError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"[ERROR] 初始化失败: {exc}", file=sys.stderr)
        return 2

    print(f"[OK] 私有工作区: {workspace}")
    print(f"[OK] 项目目录: {project_dir}")
    if backup_root:
        print(f"[OK] 已备份被替换文件: {backup_root}")
    print("[NEXT] 将授权的原始文档放入 source/chapters/，再确认云端空间与父节点。")
    print("[NOTE] 统一 CLI 默认读取 config/outline.json + state/remote_nodes.json，并兼容旧数组映射。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
