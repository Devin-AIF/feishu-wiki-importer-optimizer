#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书知识库章节批量云端同步覆写（Push）。

本脚本只负责把已准备好的 XML / Mermaid 写入已确认的节点，不再包含任何特定
书籍的推荐语、投资结论或总纲模板。如果需要覆写总纲页，请在对应的 chapter_N.json
中提供 xml 和 mermaid。
本脚本的旧有三参数 CLI 保持兼容；新增 --dry-run，建议先生成计划再执行写入。
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import atomic_write_json, backup_file, overwrite_and_render


def _is_overview(item):
    filename = str(item.get("filename", ""))
    title = str(item.get("title", ""))
    return filename == "50-总纲.md" or "总纲" in title


def _chapter_index(item):
    """保持旧版 filename 前缀 -> chapter_N.json 约定，并允许新配置显式指定 json_file。"""
    if item.get("json_file"):
        return None
    filename = str(item.get("filename", ""))
    prefix = filename.split("-", 1)[0]
    try:
        return int(prefix) - 1
    except ValueError:
        return None


def _json_path_for_item(item, json_dir):
    if item.get("json_file"):
        candidate = str(item["json_file"])
        return candidate if os.path.isabs(candidate) else os.path.join(json_dir, candidate)
    index = _chapter_index(item)
    return os.path.join(json_dir, f"chapter_{index}.json") if index is not None else None


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"章节产物必须是 JSON object: {path}")
    return data


def _validate_payload(item, data):
    obj = item.get("obj_token")
    title = item.get("title")
    xml = data.get("xml")
    if not obj or not title:
        return None, "mapping 缺少 obj_token/title"
    if not isinstance(xml, str) or not xml.strip():
        return None, "chapter JSON 缺少非空 xml"
    return {
        "title": title,
        "obj_token": obj,
        "xml": xml,
        "mermaid": data.get("mermaid"),
    }, None


def build_push_plan(mapping, json_dir):
    """从映射与已处理 JSON 组装写入计划，不触云端。"""
    plan = []
    warnings = []
    for item in sorted(mapping, key=lambda node: node.get("index", 0)):
        path = _json_path_for_item(item, json_dir)
        if not path:
            warnings.append(f"skip {item.get('title', '<unknown>')}: 无法确定 chapter JSON")
            continue
        if not os.path.exists(path):
            warnings.append(f"skip {item.get('title', '<unknown>')}: 缺少 {path}")
            continue
        try:
            data = _load_json(path)
            payload, error = _validate_payload(item, data)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"skip {item.get('title', '<unknown>')}: {exc}")
            continue
        if error:
            warnings.append(f"skip {item.get('title', '<unknown>')}: {error}")
            continue
        payload["source_path"] = path
        payload["is_overview"] = _is_overview(item)
        plan.append(payload)
    return plan, warnings


def update_maps_file(path, updates, dry_run=False):
    """仅在有新 Mermaid 源码时更新映射，写入前先备份。"""
    maps = {}
    if os.path.exists(path):
        try:
            maps = _load_json(path)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"脑图映射不可读: {exc}") from exc
    updates = {key: value for key, value in updates.items() if isinstance(value, str) and value.strip()}
    if not updates:
        return None, 0
    maps.update(updates)
    if dry_run:
        return None, len(updates)
    backup = backup_file(path)
    atomic_write_json(path, maps)
    return backup, len(updates)


def main(argv=None):
    parser = argparse.ArgumentParser(description="飞书知识库章节批量推送与白板渲染工具")
    parser.add_argument("--json-dir", required=True, help="临时章节 JSON 文件目录")
    parser.add_argument("--chapters-nodes", required=True, help="大纲配置文件 chapters_nodes.json 路径")
    parser.add_argument("--maps-file", required=True, help="脑图缓存文件 mermaid_maps.json 路径")
    parser.add_argument("--dry-run", action="store_true", help="只输出推送计划，不写入云端或本地映射")
    args = parser.parse_args(argv)

    if not os.path.exists(args.chapters_nodes):
        parser.error(f"大纲配置文件不存在: {args.chapters_nodes}")
    with open(args.chapters_nodes, "r", encoding="utf-8") as f:
        mapping = json.load(f)
    if not isinstance(mapping, list):
        parser.error("chapters_nodes 必须是 JSON 数组")

    plan, warnings = build_push_plan(mapping, args.json_dir)
    print(f"Prepared {len(plan)} chapter write(s){' [DRY-RUN]' if args.dry_run else ''}.")
    for warning in warnings:
        print(f"[WARN] {warning}")
    for payload in plan:
        kind = "overview" if payload["is_overview"] else "chapter"
        print(f"[PLAN] {kind}: {payload['title']} <- {payload['source_path']}")

    if args.dry_run:
        return 0

    mermaid_updates = {}
    failures = []
    for index, payload in enumerate(plan, start=1):
        code = payload["mermaid"]
        whiteboards = [code] if isinstance(code, str) and code.strip() else []
        print(f"Pushing [{index}/{len(plan)}] {payload['title']} ...")
        errors = overwrite_and_render(
            payload["obj_token"], payload["xml"], whiteboards, args.json_dir,
            rollback_maps={payload["title"]: code} if whiteboards else None,
            rollback_title=payload["title"],
        )
        if errors:
            failures.append(payload["title"])
            print(f"  ERROR: {errors}")
        else:
            if whiteboards:
                mermaid_updates[payload["title"]] = code
            print("  OK")

    try:
        backup, count = update_maps_file(args.maps_file, mermaid_updates)
        if count:
            print(f"Updated {count} Mermaid map(s). Backup: {backup}")
    except Exception as exc:  # noqa: BLE001
        failures.append("mermaid_maps")
        print(f"ERROR updating Mermaid maps: {exc}")

    if failures:
        print(f"Completed with {len(failures)} failure(s): {failures}")
        return 1
    print("All planned writes completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
