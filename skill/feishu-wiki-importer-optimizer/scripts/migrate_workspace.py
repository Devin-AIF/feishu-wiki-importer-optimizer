#!/usr/bin/env python3
"""将旧版私有运行目录离线迁移为 projects/<slug>/ 分层工作区。

默认只做预检。显式使用 ``--apply`` 后会先在同一文件系统中构建并逐文件
校验新结构，再切换项目目录。旧目录只移入 ``archives/``，不会删除。
本脚本不导入业务模块、不调用 lark-cli，也不访问网络。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SCRIPT_DIR.parents[2]
PROJECT_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
CHAPTER_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$")

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


class MigrationError(RuntimeError):
    """迁移预检或校验失败。"""


def _default_workspace() -> Path:
    adjacent = Path(f"{REPO_ROOT}.private-workspace")
    if adjacent.is_dir():
        return adjacent.resolve()
    state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    base = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    return (base / "feishu-wiki-importer-optimizer").resolve()


def resolve_workspace(explicit: Optional[str]) -> Path:
    raw = explicit or os.environ.get("FEISHU_WIKI_WORKSPACE", "").strip()
    workspace = Path(raw).expanduser().resolve() if raw else _default_workspace()
    if workspace in (Path(workspace.anchor), Path.home().resolve()):
        raise MigrationError("拒绝将根目录或用户 HOME 作为工作区")
    if workspace == REPO_ROOT or REPO_ROOT in workspace.parents:
        raise MigrationError("私有工作区不得位于开发仓库内")
    if workspace == SKILL_DIR or SKILL_DIR in workspace.parents:
        raise MigrationError("私有工作区不得位于可发布 Skill 内")
    if not workspace.is_dir():
        raise MigrationError(f"工作区不存在: {workspace}")
    return workspace


def validate_project(value: str) -> str:
    if not PROJECT_SLUG_RE.fullmatch(str(value or "")):
        raise MigrationError("项目名必须是 1-64 位小写字母、数字或连字符")
    return value


def _load_json(path: Path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError(f"JSON 不可读: {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _secure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def _write_json(path: Path, data) -> None:
    _secure_directory(path.parent)
    fd, temp_name = tempfile.mkstemp(prefix=".migration-", suffix=".json", dir=path.parent)
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


def _safe_source_path(item: dict) -> Optional[str]:
    raw = item.get("filepath") or item.get("filename")
    if raw in (None, ""):
        return None
    value = str(raw).replace("\\", "/")
    if value.startswith("/") or any(part == ".." for part in value.split("/")):
        raise MigrationError("旧映射包含不安全原稿路径")
    if not value.startswith("chapters/"):
        value = "chapters/" + value.lstrip("./")
    return value


def _chapter_id(item: dict, used: set) -> str:
    existing = item.get("chapter_id")
    if isinstance(existing, str) and CHAPTER_ID_RE.fullmatch(existing) and existing not in used:
        used.add(existing)
        return existing
    index = item.get("index")
    if not isinstance(index, int) or index < 0:
        raise MigrationError("旧映射的 index 必须是非负整数")
    candidate = f"chapter-{index + 1:03d}"
    if candidate in used:
        raise MigrationError("旧映射 index 重复，无法生成稳定 chapter_id")
    used.add(candidate)
    return candidate


def split_legacy_mapping(mapping: list, maps: dict) -> Tuple[dict, dict, dict]:
    if not isinstance(mapping, list) or not mapping:
        raise MigrationError("chapters_nodes.json 必须是非空 JSON 数组")
    if not isinstance(maps, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in maps.items()
    ):
        raise MigrationError("mermaid_maps.json 必须是字符串到字符串的 JSON object")

    used = set()
    title_to_id: Dict[str, str] = {}
    normalized: List[Tuple[dict, str]] = []
    for position, item in enumerate(mapping):
        if not isinstance(item, dict):
            raise MigrationError(f"旧映射第 {position} 项不是 object")
        title = item.get("title")
        if not isinstance(title, str) or not title.strip() or title in title_to_id:
            raise MigrationError("旧映射标题必须非空且不重复")
        chapter_id = _chapter_id(item, used)
        title_to_id[title] = chapter_id
        normalized.append((item, chapter_id))

    chapters = []
    nodes = {}
    for item, chapter_id in normalized:
        filename = str(item.get("filename") or "")
        title = item["title"]
        parent_id = item.get("parent_chapter_id")
        if not parent_id and item.get("parent_title"):
            parent_id = title_to_id.get(item["parent_title"])
            if not parent_id:
                raise MigrationError("旧映射 parent_title 找不到对应章节")
        if parent_id is not None and parent_id not in used:
            raise MigrationError("旧映射 parent_chapter_id 无对应章节")
        kind = "overview" if filename == "50-总纲.md" or "总纲" in title else "article"
        chapters.append(
            {
                "chapter_id": chapter_id,
                "index": item["index"],
                "title": title,
                "kind": kind,
                "parent_chapter_id": parent_id,
                "source_path": _safe_source_path(item),
            }
        )
        nodes[chapter_id] = {
            "node_token": item.get("node_token") or None,
            "obj_token": item.get("obj_token") or None,
            "last_seen_at": None,
        }

    unmatched = sorted(set(maps) - set(title_to_id))
    if unmatched:
        raise MigrationError(
            f"mermaid_maps.json 有 {len(unmatched)} 个标题无法关联 chapter_id，已在写入前中止"
        )
    migrated_maps = {title_to_id[title]: code for title, code in maps.items()}
    outline = {"schema_version": 1, "chapters": chapters}
    remote = {
        "schema_version": 1,
        "space_id": None,
        "parent_node_token": None,
        "parent_obj_token": None,
        "nodes": nodes,
    }
    return outline, remote, migrated_maps


def _legacy_json_name(item: dict) -> Optional[str]:
    explicit = item.get("json_file")
    if isinstance(explicit, str) and explicit and not Path(explicit).is_absolute():
        return Path(explicit).name
    filename = str(item.get("filename") or "")
    prefix = filename.split("-", 1)[0]
    try:
        index = int(prefix) - 1
    except ValueError:
        index = item.get("index")
    if not isinstance(index, int) or index < 0:
        return None
    return f"chapter_{index}.json"


def _prepared_matches(path: Path, chapter_id: str, title: str) -> bool:
    try:
        data = _load_json(path)
    except MigrationError:
        return False
    if not isinstance(data, dict):
        return False
    payload_id = data.get("chapter_id")
    if payload_id:
        return payload_id == chapter_id
    payload_title = data.get("title")
    if not isinstance(payload_title, str) or not payload_title.strip():
        xml = data.get("xml")
        if not isinstance(xml, str):
            return False
        match = re.search(r"<title(?:\s[^>]*)?>(.*?)</title>", xml, flags=re.I | re.S)
        if not match:
            return False
        payload_title = re.sub(r"<[^>]+>", "", match.group(1))
        payload_title = unescape(payload_title).strip()
    return payload_title.strip() == title.strip()


def _iter_regular_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    files = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise MigrationError(f"待迁移目录包含符号链接，拒绝跟随: {path}")
        if path.is_file():
            files.append(path)
    return files


def _copy_files(
    source: Path,
    destination: Path,
    manifest: List[dict],
    include=None,
) -> None:
    if not source.exists():
        return
    if not source.is_dir() or source.is_symlink():
        raise MigrationError(f"待迁移路径不是安全目录: {source}")
    _secure_directory(destination)
    for source_file in _iter_regular_files(source):
        relative = source_file.relative_to(source)
        if include is not None and not include(relative):
            continue
        target = destination / relative
        _secure_directory(target.parent)
        shutil.copy2(source_file, target)
        target.chmod(0o600)
        source_hash = _sha256(source_file)
        if _sha256(target) != source_hash:
            raise MigrationError(f"复制后 checksum 不一致: {relative}")
        manifest.append(
            {
                "source": str(source_file.relative_to(source.parent)),
                "destination": str(target),
                "sha256": source_hash,
                "size": source_file.stat().st_size,
            }
        )


def _secure_tree(root: Path) -> None:
    if not root.exists():
        return
    for path in [root] + sorted(root.rglob("*")):
        if path.is_symlink():
            continue
        if path.is_dir():
            path.chmod(0o700)
        elif path.is_file():
            path.chmod(0o600)


def _preflight(workspace: Path, project: str):
    mapping_path = workspace / "mappings" / "chapters_nodes.json"
    maps_path = workspace / "mappings" / "mermaid_maps.json"
    if (workspace / "workspace.json").exists():
        raise MigrationError("workspace.json 已存在，拒绝覆盖可能已迁移的工作区")
    if (workspace / "projects" / project).exists():
        raise MigrationError(f"目标项目已存在，拒绝覆盖: {project}")
    if not mapping_path.is_file() or not maps_path.is_file():
        raise MigrationError("缺少 mappings/chapters_nodes.json 或 mermaid_maps.json")
    mapping = _load_json(mapping_path)
    maps = _load_json(maps_path)
    outline, remote, migrated_maps = split_legacy_mapping(mapping, maps)
    bindings = {}
    for legacy, chapter in zip(mapping, outline["chapters"]):
        json_name = _legacy_json_name(legacy)
        if json_name:
            bindings[json_name] = (chapter["chapter_id"], chapter["title"])
    prepared_candidates = list((workspace / "scratch").glob("chapter_*.json"))
    verified_prepared = {
        path.name
        for path in prepared_candidates
        if path.name in bindings and _prepared_matches(path, *bindings[path.name])
    }
    return (
        mapping_path,
        maps_path,
        outline,
        remote,
        migrated_maps,
        prepared_candidates,
        verified_prepared,
    )


def migrate(workspace: Path, project: str, apply: bool = False) -> dict:
    (
        mapping_path,
        maps_path,
        outline,
        remote,
        migrated_maps,
        prepared_candidates,
        verified_prepared,
    ) = _preflight(workspace, project)
    plan = {
        "project": project,
        "chapters": len(outline["chapters"]),
        "remote_nodes": len(remote["nodes"]),
        "mermaid_maps": len(migrated_maps),
        "prepared_candidates": len(prepared_candidates),
        "prepared_verified": len(verified_prepared),
        "prepared_quarantined": len(prepared_candidates) - len(verified_prepared),
        "apply": apply,
    }
    if not apply:
        return plan

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    stage = Path(tempfile.mkdtemp(prefix=".migration-stage-", dir=workspace))
    project_stage = stage / "projects" / project
    manifest: List[dict] = []
    try:
        _secure_directory(project_stage)
        for relative in PROJECT_DIRECTORIES:
            _secure_directory(project_stage / relative)

        _copy_files(workspace / "chapters", project_stage / "source" / "chapters", manifest)
        _copy_files(workspace / "temp_images", project_stage / "source" / "images", manifest)
        _copy_files(
            workspace / "scratch",
            project_stage / "generated" / "prepared",
            manifest,
            include=lambda relative: relative.name in verified_prepared,
        )
        _copy_files(
            workspace / "runtime_backups",
            project_stage / "backups" / "runtime",
            manifest,
        )
        _copy_files(workspace / "previews", project_stage / "previews", manifest)

        uploaded_images = {}
        legacy_uploaded = workspace / "mappings" / "uploaded_images.json"
        if legacy_uploaded.exists():
            uploaded_images = _load_json(legacy_uploaded)
            if not isinstance(uploaded_images, dict):
                raise MigrationError("uploaded_images.json 必须是 JSON object")

        _write_json(stage / "workspace.json", {"schema_version": 1, "default_project": project})
        _write_json(
            project_stage / "project.json",
            {"schema_version": 1, "project_id": project, "display_name": project},
        )
        _write_json(project_stage / "config" / "outline.json", outline)
        _write_json(project_stage / "state" / "remote_nodes.json", remote)
        _write_json(project_stage / "state" / "uploaded_images.json", uploaded_images)
        _write_json(project_stage / "generated" / "mermaid_maps.json", migrated_maps)

        # 再读一次所有核心 JSON，确认切换前仍可解析。
        for path in (
            stage / "workspace.json",
            project_stage / "project.json",
            project_stage / "config" / "outline.json",
            project_stage / "state" / "remote_nodes.json",
            project_stage / "state" / "uploaded_images.json",
            project_stage / "generated" / "mermaid_maps.json",
        ):
            _load_json(path)

        for item in manifest:
            relative = Path(item["destination"]).relative_to(project_stage)
            item["destination"] = str(Path("projects") / project / relative)

        _secure_directory(workspace / "projects")
        final_project = workspace / "projects" / project
        os.replace(project_stage, final_project)
        os.replace(stage / "workspace.json", workspace / "workspace.json")
        (workspace / "workspace.json").chmod(0o600)

        migration_root = workspace / "archives" / "migrations" / stamp
        legacy_root = migration_root / "legacy-layout"
        _secure_directory(legacy_root)
        archived = []
        for name in (
            "chapters",
            "temp_images",
            "scratch",
            "mappings",
            "runtime_backups",
            "previews",
            "cache",
        ):
            source = workspace / name
            if source.exists():
                destination = legacy_root / name
                os.replace(source, destination)
                archived.append(str(destination.relative_to(workspace)))

        for name, destination in (
            ("verification", workspace / "archives" / "verification"),
            ("legacy-archive", workspace / "archives" / "legacy"),
        ):
            source = workspace / name
            if source.exists():
                if destination.exists():
                    raise MigrationError(f"归档目标已存在: {destination}")
                _secure_directory(destination.parent)
                os.replace(source, destination)
                archived.append(str(destination.relative_to(workspace)))

        _secure_tree(final_project)
        _secure_tree(workspace / "archives")
        report = {
            "schema_version": 1,
            "completed_at": stamp,
            "project": project,
            "source_mapping_sha256": _sha256(
                legacy_root / "mappings" / mapping_path.name
            ),
            "source_mermaid_maps_sha256": _sha256(
                legacy_root / "mappings" / maps_path.name
            ),
            "copied_file_count": len(manifest),
            "copied_bytes": sum(item["size"] for item in manifest),
            "prepared_candidates": len(prepared_candidates),
            "prepared_verified": len(verified_prepared),
            "prepared_quarantined": len(prepared_candidates) - len(verified_prepared),
            "archived_paths": archived,
            "files": manifest,
        }
        _write_json(migration_root / "migration-report.json", report)
        plan.update(
            {
                "migration": str(migration_root),
                "copied_files": len(manifest),
                "archived_paths": len(archived),
            }
        )
        return plan
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="将旧私有运行目录安全迁移到 projects/<slug>/（完全离线）"
    )
    parser.add_argument("--workspace", help="私有工作区路径")
    parser.add_argument("--project", default="default", help="目标项目 slug（默认 default）")
    parser.add_argument("--apply", action="store_true", help="通过预检后实际迁移；默认只显示计划")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        workspace = resolve_workspace(args.workspace)
        project = validate_project(args.project)
        result = migrate(workspace, project, apply=args.apply)
    except MigrationError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(
        f"[{mode}] project={result['project']} chapters={result['chapters']} "
        f"nodes={result['remote_nodes']} maps={result['mermaid_maps']} "
        f"prepared={result['prepared_verified']}/{result['prepared_candidates']}"
    )
    if args.apply:
        print(
            f"[OK] copied_files={result['copied_files']} "
            f"archived_paths={result['archived_paths']}"
        )
        print(f"[OK] migration_report={result['migration']}/migration-report.json")
    else:
        print("[NEXT] 确认已完成工作区外部备份后，显式追加 --apply。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
