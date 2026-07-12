"""本地 JSON、备份与新旧章节映射存储。"""

import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone

from . import paths


def _secure_directory(path):
    os.makedirs(path, mode=0o700, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def backup_file(path, backup_dir=None):
    """备份单个本地文件，返回备份路径。"""
    if not path or not os.path.exists(path):
        return None
    backup_dir = backup_dir or os.path.join(
        os.path.dirname(os.path.abspath(path)), "backups"
    )
    _secure_directory(backup_dir)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = os.path.join(
        backup_dir, "%s.%s.bak" % (os.path.basename(path), stamp)
    )
    shutil.copy2(path, destination)
    try:
        os.chmod(destination, 0o600)
    except OSError:
        pass
    return destination


def atomic_write_json(path, data):
    """在同一目录中原子替换 JSON，避免中途异常损坏配置。"""
    target_dir = os.path.dirname(os.path.abspath(path))
    _secure_directory(target_dir)
    fd, temp_path = tempfile.mkstemp(
        prefix=".tmp_", suffix=".json", dir=target_dir
    )
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def _load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_mermaid_maps(path=None):
    """加载 Mermaid 映射；文件缺失或无效时安全返回空字典。"""
    path = path or paths.MERMAID_MAPS_PATH
    if not os.path.exists(path):
        return {}
    try:
        data = _load_json(path)
        if not isinstance(data, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in data.items()
        ):
            raise ValueError("脑图映射必须是字符串到字符串的 JSON object")
        return data
    except Exception as exc:  # noqa: BLE001
        print("WARNING: Failed to load Mermaid map %s: %s" % (path, exc))
        return {}


def find_mermaid_key(title, maps, chapter_id=None):
    """优先用稳定 chapter_id，再兼容历史标题键。"""
    if not maps:
        return None
    if chapter_id and chapter_id in maps:
        return chapter_id
    if not title:
        return None
    if title in maps:
        return title
    match = re.search(r"#\s*(\d+)", title)
    if match:
        number = match.group(1)
        numeric_key = "#" + number
        if numeric_key in maps:
            return numeric_key
        for key in maps:
            if re.search(r"#\s*" + re.escape(number) + r"\b", key):
                prefix = re.split(r"#\s*\d+", key)[0].strip()
                if not prefix or prefix in title:
                    return key
    for key in maps:
        if re.search(r"#\s*\d+", key):
            continue
        if key and key in title:
            return key
    return None


def _validate_mapping_items(data, path):
    if not isinstance(data, list):
        raise ValueError("Node mapping must be a JSON array: %s" % path)
    for position, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError("Mapping item #%s must be an object" % position)
        if "index" not in item or "title" not in item:
            raise ValueError("Mapping item #%s is missing index/title" % position)
    return data


def _remote_path_for_outline(outline_path):
    config_dir = os.path.dirname(os.path.abspath(outline_path))
    project_dir = os.path.dirname(config_dir)
    return os.path.join(project_dir, "state", "remote_nodes.json")


def _load_remote_state(outline_path):
    state_path = _remote_path_for_outline(outline_path)
    if not os.path.exists(state_path):
        return state_path, {
            "schema_version": 1,
            "space_id": None,
            "parent_node_token": None,
            "parent_obj_token": None,
            "nodes": {},
        }
    state = _load_json(state_path)
    if not isinstance(state, dict) or not isinstance(state.get("nodes"), dict):
        raise ValueError("remote_nodes.json 必须是含 nodes object 的 JSON object")
    return state_path, state


def _merge_project_mapping(outline_path, outline):
    chapters = outline.get("chapters") if isinstance(outline, dict) else None
    if not isinstance(chapters, list):
        raise ValueError("outline.json 必须是含 chapters 数组的 JSON object")
    _, remote = _load_remote_state(outline_path)
    nodes = remote.get("nodes", {})
    merged = []
    seen = set()
    for position, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            raise ValueError("Outline chapter #%s must be an object" % position)
        chapter_id = chapter.get("chapter_id")
        if not isinstance(chapter_id, str) or not chapter_id or chapter_id in seen:
            raise ValueError("Outline chapter #%s has invalid/duplicate chapter_id" % position)
        seen.add(chapter_id)
        item = dict(chapter)
        source_path = item.get("source_path")
        if isinstance(source_path, str) and source_path:
            item.setdefault("filepath", source_path)
            item.setdefault("filename", os.path.basename(source_path))
        node = nodes.get(chapter_id, {})
        if isinstance(node, dict):
            item["node_token"] = node.get("node_token")
            item["obj_token"] = node.get("obj_token")
        merged.append(item)
    return _validate_mapping_items(merged, outline_path)


def resolve_mapping(explicit=None):
    """解析新 outline+state 或旧 chapters_nodes 映射。"""
    path = os.path.abspath(os.path.expanduser(explicit or paths.DEFAULT_MAPPING_PATH))
    if not os.path.exists(path):
        print("Error: Node mapping JSON not found: %s" % path)
        sys.exit(1)
    data = _load_json(path)
    if isinstance(data, list):
        return path, _validate_mapping_items(data, path)
    if isinstance(data, dict) and "chapters" in data:
        return path, _merge_project_mapping(path, data)
    raise ValueError(
        "Node mapping must be a legacy JSON array or project outline object: %s" % path
    )


def mapping_metadata(mapping_path):
    """返回新项目 remote_nodes 的云端上下文；旧格式返回空字典。"""
    data = _load_json(mapping_path)
    if not isinstance(data, dict) or "chapters" not in data:
        return {}
    _, state = _load_remote_state(mapping_path)
    return {
        "space_id": state.get("space_id"),
        "parent_node_token": state.get("parent_node_token"),
        "parent_obj_token": state.get("parent_obj_token"),
    }


def save_mapping_state(
    mapping_path,
    mapping,
    space_id=None,
    parent_node_token=None,
    parent_obj_token=None,
):
    """回写建档状态：新格式只写 state，旧格式保持数组兼容。"""
    source = _load_json(mapping_path)
    if isinstance(source, list):
        backup = backup_file(mapping_path)
        atomic_write_json(mapping_path, mapping)
        return backup
    if not isinstance(source, dict) or "chapters" not in source:
        raise ValueError("Unsupported mapping format: %s" % mapping_path)

    state_path, state = _load_remote_state(mapping_path)
    nodes = dict(state.get("nodes", {}))
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for item in mapping:
        chapter_id = item.get("chapter_id")
        if not chapter_id:
            raise ValueError("Project mapping item is missing chapter_id")
        previous = nodes.get(chapter_id, {})
        if not isinstance(previous, dict):
            previous = {}
        node_token = item.get("node_token") or None
        obj_token = item.get("obj_token") or None
        changed = (
            node_token != previous.get("node_token")
            or obj_token != previous.get("obj_token")
        )
        nodes[chapter_id] = {
            "node_token": node_token,
            "obj_token": obj_token,
            "last_seen_at": (
                now if changed and (node_token or obj_token) else previous.get("last_seen_at")
            ),
        }
    state = dict(state)
    state["schema_version"] = 1
    state["nodes"] = nodes
    if space_id:
        state["space_id"] = space_id
    if parent_node_token:
        state["parent_node_token"] = parent_node_token
    if parent_obj_token:
        state["parent_obj_token"] = parent_obj_token

    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(mapping_path)))
    backup_dir = os.path.join(project_dir, "backups", "state")
    backup = backup_file(state_path, backup_dir=backup_dir)
    atomic_write_json(state_path, state)
    return backup
