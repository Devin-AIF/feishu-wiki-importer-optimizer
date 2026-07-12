"""飞书知识库导入与排版的统一 CLI 实现。"""

import argparse
import importlib
import os
import re
import shutil
import sys
import time
from html import escape

from . import lark_client, paths, service, whiteboards, writer
from .storage import (
    find_mermaid_key,
    load_mermaid_maps,
    mapping_metadata,
    resolve_mapping,
    save_mapping_state,
)


def _workflow_module(name):
    """按需加载工作流，避免主 CLI 启动时引入无关依赖。"""
    return importlib.import_module(name)


def cmd_create_nodes(args):
    mapping_path, mapping = resolve_mapping(args.mapping)
    metadata = mapping_metadata(mapping_path)
    existing = {}
    if args.dry_run:
        space = parent = None
    else:
        space = (
            args.space
            or metadata.get("space_id")
            or input("请输入飞书知识库空间 ID (space_id): ").strip()
        )
        parent = (
            args.parent
            or metadata.get("parent_node_token")
            or input("请输入父节点挂载标识符 (parent_node_id): ").strip()
        )
        if not space or not parent:
            print("Error: space_id 和 parent_node_id 为必填参数。")
            sys.exit(1)
        try:
            existing = lark_client.api_get_nodes(space, parent)
        except lark_client.NodeScanError as exc:
            print("ERROR: 预扫描现有子节点失败，为避免重复建档已中止：%s" % exc)
            sys.exit(2)

    updated = []
    for item in sorted(mapping, key=lambda node: node["index"]):
        title = item["title"]
        display_index = item["index"] + 1
        if item.get("obj_token") and item.get("node_token"):
            print("[%02d] SKIP (exists): %s" % (display_index, title))
            updated.append(item)
            continue
        if title in existing:
            item["node_token"], item["obj_token"] = existing[title]
            print("[%02d] REUSE: %s" % (display_index, title))
            updated.append(item)
            continue
        if args.dry_run:
            print("[%02d] [DRY-RUN] CREATE: %s" % (display_index, title))
            updated.append(item)
            continue
        result = lark_client.api_create_node(space, parent, title)
        if result.get("ok"):
            data = result.get("data", {})
            item["node_token"] = data.get("node_token")
            item["obj_token"] = data.get("obj_token")
            print("[%02d] CREATED: %s (obj: %s)" % (display_index, title, item["obj_token"]))
        else:
            try:
                recovered = lark_client.api_get_nodes(space, parent)
            except lark_client.NodeScanError as scan_error:
                print(
                    "[%02d] FAILED: %s: %s; 后续扫描失败，未重试创建: %s"
                    % (display_index, title, result.get("error"), scan_error)
                )
                updated.append(item)
                break
            if title in recovered:
                item["node_token"], item["obj_token"] = recovered[title]
                print("[%02d] REUSE after uncertain create: %s" % (display_index, title))
            else:
                print("[%02d] FAILED: %s: %s" % (display_index, title, result.get("error")))
        updated.append(item)

    updated.sort(key=lambda node: node["index"])
    if args.dry_run:
        print("\n[DRY-RUN] Mapping file untouched.")
    else:
        backup = save_mapping_state(
            mapping_path,
            updated,
            space_id=space,
            parent_node_token=parent,
        )
        print("\nBatch creation finished. Mapping updated. Backup: %s" % backup)
    return 0


def build_sub_page_xml(mapping, space_id, parent_wiki_node):
    wiki_token_attribute = "wiki" + "-" + "token"
    lines = [
        '<sub-page-list space-id="%s" %s="%s">'
        % (
            escape(str(space_id), quote=True),
            wiki_token_attribute,
            escape(str(parent_wiki_node), quote=True),
        )
    ]
    for item in sorted(mapping, key=lambda node: node["index"]):
        title = item["title"]
        obj_token = item.get("obj_token")
        if obj_token:
            lines.append(
                '    <sub-page doc-id="%s" file-type="docx" title="%s"/>'
                % (
                    escape(str(obj_token), quote=True),
                    escape(str(title), quote=True),
                )
            )
    lines.append("</sub-page-list>")
    return "\n".join(lines)


def cmd_update_nav(args):
    mapping_path, mapping = resolve_mapping(args.mapping)
    metadata = mapping_metadata(mapping_path)
    space = args.space or metadata.get("space_id") or input("space_id: ").strip()
    parent_obj = (
        args.parent_obj
        or metadata.get("parent_obj_token")
        or input("父节点文档 obj_token: ").strip()
    )
    parent_node = (
        args.parent_node
        or metadata.get("parent_node_token")
        or input("父节点目录 node_token: ").strip()
    )
    if not (space and parent_obj and parent_node):
        print("Error: space_id / parent_obj / parent_node are all required.")
        sys.exit(1)
    output = lark_client.api_fetch(parent_obj)
    if not output or not output.get("ok"):
        print("Error fetching parent doc: %s" % (output.get("error") if output else "unknown"))
        sys.exit(1)
    original_content = output.get("data", {}).get("document", {}).get("content", "")
    maps = load_mermaid_maps(args.maps)
    parent_map_key = None
    for item in mapping:
        if item.get("obj_token") == parent_obj:
            parent_map_key = find_mermaid_key(
                item.get("title"), maps, chapter_id=item.get("chapter_id")
            )
            break
    try:
        content, original_whiteboards = whiteboards.prepare_document_whiteboards_for_overwrite(
            original_content, maps=maps, chapter_title=parent_map_key
        )
    except whiteboards.WhiteboardSourceError as exc:
        print("ERROR updating parent document safely: %s" % exc)
        return 1

    sub_xml = build_sub_page_xml(mapping, space, parent_node)
    cleaned = re.sub(
        r"<sub-page-list[^>]*?>.*?</sub-page-list>", "", content, flags=re.DOTALL
    )
    heading_pattern = r"(<h2>[^<]*?五、\s*.*?</h2>)"
    if re.search(heading_pattern, cleaned):
        updated = re.sub(heading_pattern, r"\1\n" + sub_xml, cleaned, count=1)
        print("Located nav header (五、). Sub-pages mounted under it.")
    else:
        updated = (
            cleaned + "\n" + sub_xml
            if cleaned.endswith("</title>")
            else cleaned + "\n<h2>五、 子页面导航</h2>\n" + sub_xml
        )
        print("No nav header found. Mounted at end of document.")
    if args.dry_run:
        os.makedirs(paths.PREVIEW_DIR, exist_ok=True)
        preview = os.path.join(paths.PREVIEW_DIR, "dryrun_top_node_preview.xml")
        with open(preview, "w", encoding="utf-8") as handle:
            handle.write(updated)
        print("[DRY-RUN] Preview written to: %s" % preview)
        return 0
    errors = writer.overwrite_and_render(
        parent_obj,
        updated,
        original_whiteboards,
        paths.TEMP_DIR,
        original_xml=original_content,
        rollback_maps=maps,
        rollback_title=parent_map_key,
    )
    if errors:
        print("ERROR updating parent document: %s" % errors)
        return 1
    else:
        print("Success! Parent page navigation updated.")
        return 0


def process_one(item, mode, cache_dir, xml_temp, dry_run, maps_path=None):
    obj_token = item.get("obj_token")
    title = item.get("title")
    if not obj_token or not title:
        return None
    filepath = service.fetch_node_to_cache(obj_token, title, cache_dir)
    if not filepath:
        return title
    try:
        result = service.process_chapter_file(
            filepath,
            xml_temp,
            mode=mode,
            dry_run=dry_run,
            chapter_title=title,
            chapter_id=item.get("chapter_id"),
            maps_path=maps_path,
        )
        return title if result.get("errors") else None
    except Exception as exc:  # noqa: BLE001
        print("ERROR %s: %s" % (title, exc))
        return title


def run_batch(mode, args, workers=1):
    _, mapping = resolve_mapping(args.mapping)
    cache_dir = os.path.join(paths.TEMP_DIR, "temp_%s_cache" % mode)
    xml_temp = os.path.join(paths.TEMP_DIR, "temp_%s_xml" % mode)
    os.makedirs(cache_dir, exist_ok=True)
    os.makedirs(xml_temp, exist_ok=True)
    mode_label = "LIVE" if not args.dry_run else "DRY-RUN (no cloud writes)"
    print(
        "[%s] Processing %s nodes [%s] with %s worker(s) ..."
        % (mode, len(mapping), mode_label, max(1, workers))
    )
    started = time.time()
    failures = []
    items = [item for item in mapping if item.get("obj_token") and item.get("title")]
    workers = max(1, workers)
    if workers == 1:
        for item in items:
            failed = process_one(item, mode, cache_dir, xml_temp, args.dry_run, args.maps)
            if failed:
                failures.append(failed)
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for failed in executor.map(
                lambda item: process_one(
                    item, mode, cache_dir, xml_temp, args.dry_run, args.maps
                ),
                items,
            ):
                if failed:
                    failures.append(failed)
    shutil.rmtree(cache_dir, ignore_errors=True)
    shutil.rmtree(xml_temp, ignore_errors=True)
    print("=" * 60)
    print("[%s] Completed in %.2fs." % (mode, time.time() - started))
    if failures:
        print("WARNING: %s node(s) had errors: %s" % (len(failures), failures))
    if args.dry_run:
        print("Previews written to: %s" % paths.PREVIEW_DIR)
    return 1 if failures else 0


def cmd_polish(args):
    return run_batch("polish", args, workers=args.workers)


def cmd_restore_wb(args):
    return run_batch("whiteboard", args, workers=args.workers)


def cmd_prepare(args):
    module = _workflow_module("feishu_wiki.prepare")
    argv = [
        "--workspace", paths.RUNTIME_DIR,
        "--project", paths.PROJECT,
        "--md-dir", args.md_dir or paths.SOURCE_CHAPTERS_DIR,
        "--json-dir", args.json_dir or paths.PREPARED_DIR,
        "--mapping", args.mapping or paths.DEFAULT_MAPPING_PATH,
        "--uploaded-images", args.uploaded_images or paths.UPLOADED_IMAGES_PATH,
    ]
    if args.dry_run:
        argv.append("--dry-run")
    return module.main(argv)


def cmd_push(args):
    module = _workflow_module("feishu_wiki.push")
    argv = [
        "--workspace", paths.RUNTIME_DIR,
        "--project", paths.PROJECT,
        "--json-dir", args.json_dir or paths.PREPARED_DIR,
        "--mapping", args.mapping or paths.DEFAULT_MAPPING_PATH,
        "--maps-file", args.maps_file or paths.MERMAID_MAPS_PATH,
    ]
    if args.dry_run:
        argv.append("--dry-run")
    if args.allow_partial:
        argv.append("--allow-partial")
    return module.main(argv)


def build_parser():
    parser = argparse.ArgumentParser(
        description="飞书知识库文献排版打磨与建档统一工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--workspace", help="私有工作区（优先级高于环境变量）")
    parser.add_argument("--project", help="项目 slug（默认读 workspace.json）")
    subcommands = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--mapping", default=None, help="大纲映射（默认项目 config/outline.json + state）")
    common.add_argument("--maps", default=None, help="Mermaid 映射（默认项目 generated/mermaid_maps.json）")
    common.add_argument("--dry-run", action="store_true", help="只生成预览，不触碰云端")
    command = subcommands.add_parser("create-nodes", parents=[common], help="批量建档（幂等去重）并回写 Token")
    command.add_argument("--space", default=None, help="知识库空间 ID")
    command.add_argument("--parent", default=None, help="父节点挂载标识符")
    command.set_defaults(func=cmd_create_nodes)
    command = subcommands.add_parser("update-nav", parents=[common], help="挂载父页面原生子页面导航")
    command.add_argument("--space", default=None, help="知识库空间 ID")
    command.add_argument("--parent-obj", default=None, help="父页面文档对象标识")
    command.add_argument("--parent-node", default=None, help="父目录节点标识")
    command.set_defaults(func=cmd_update_nav)
    command = subcommands.add_parser("polish", parents=[common], help="一站式排版打磨（含白板防丢重绘）")
    command.add_argument("--workers", type=int, default=1, help="并发数（默认 1，建议 <=5）")
    command.set_defaults(func=cmd_polish)
    command = subcommands.add_parser("restore-wb", parents=[common], help="仅重绘/补全白板脑图")
    command.add_argument("--workers", type=int, default=1, help="并发数（默认 1，建议 <=5）")
    command.set_defaults(func=cmd_restore_wb)
    command = subcommands.add_parser(
        "prepare", help="将本地 Markdown 合并到已生成的章节 JSON"
    )
    command.add_argument("--md-dir", help="原稿目录（默认 source/chapters）")
    command.add_argument("--json-dir", help="章节 JSON 目录（默认 generated/prepared）")
    command.add_argument("--mapping", "--chapters-nodes", dest="mapping", help="大纲映射（兼容旧数组）")
    command.add_argument("--uploaded-images", help="图片上传状态 JSON")
    command.add_argument("--dry-run", action="store_true", help="只生成本地预览，不上传图片/覆盖 JSON")
    command.set_defaults(func=cmd_prepare)
    command = subcommands.add_parser(
        "push", help="将已准备的章节 JSON 覆写到已确认的飞书节点"
    )
    command.add_argument("--json-dir", help="已准备章节 JSON 目录（默认 generated/prepared）")
    command.add_argument("--mapping", "--chapters-nodes", dest="mapping", help="大纲映射（兼容旧数组）")
    command.add_argument("--maps-file", help="Mermaid 映射 JSON")
    command.add_argument("--dry-run", action="store_true", help="只输出计划，不写云端/本地映射")
    command.add_argument("--allow-partial", action="store_true", help="明确允许跳过预检失败的章节")
    command.set_defaults(func=cmd_push)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        paths.configure(args.workspace, args.project)
    except paths.WorkspacePathError as exc:
        parser.error(str(exc))
    return args.func(args)
