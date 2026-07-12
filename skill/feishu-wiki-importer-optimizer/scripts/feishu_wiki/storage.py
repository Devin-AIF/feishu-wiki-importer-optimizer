"""本地 JSON、备份与旧映射文件存储。"""

import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime

from .paths import DEFAULT_MAPPING_PATH, MERMAID_MAPS_PATH


def backup_file(path, backup_dir=None):
    """备份单个本地文件，返回备份路径。"""
    if not path or not os.path.exists(path):
        return None
    backup_dir = backup_dir or os.path.join(
        os.path.dirname(os.path.abspath(path)), "backups"
    )
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = os.path.join(
        backup_dir, "%s.%s.bak" % (os.path.basename(path), stamp)
    )
    shutil.copy2(path, destination)
    return destination


def atomic_write_json(path, data):
    """在同一目录中原子替换 JSON，避免中途异常损坏配置。"""
    target_dir = os.path.dirname(os.path.abspath(path))
    os.makedirs(target_dir, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=".tmp_", suffix=".json", dir=target_dir
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def load_mermaid_maps(path=None):
    """加载 Mermaid 映射；文件缺失或无效时安全返回空字典。"""
    path = path or MERMAID_MAPS_PATH
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("脑图映射必须是 JSON object")
        return data
    except Exception as exc:  # noqa: BLE001
        print("WARNING: Failed to load Mermaid map %s: %s" % (path, exc))
        return {}


def find_mermaid_key(title, maps):
    """精确匹配章节标题对应的 Mermaid 键。"""
    if not maps or not title:
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


def resolve_mapping(explicit=None):
    """解析旧章节映射文件，返回 `(路径, 数组)`。"""
    path = explicit or DEFAULT_MAPPING_PATH
    if not os.path.exists(path):
        print("Error: Node mapping JSON not found: %s" % path)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("Node mapping must be a JSON array: %s" % path)
    for position, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError("Mapping item #%s must be an object" % position)
        if "index" not in item or "title" not in item:
            raise ValueError("Mapping item #%s is missing index/title" % position)
    return path, data
