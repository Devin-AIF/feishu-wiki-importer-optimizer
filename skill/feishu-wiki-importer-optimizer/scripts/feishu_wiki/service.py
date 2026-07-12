"""单章节排版/白板处理与云端文档缓存编排。"""

import hashlib
import json
import os
import re
import sys

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.stderr.write("\n[ERROR] 缺少依赖 beautifulsoup4。\n\n")
    sys.exit(2)

from . import lark_client, transforms, whiteboards, writer
from .paths import PREVIEW_DIR
from .storage import find_mermaid_key, load_mermaid_maps


def process_chapter_file(
    filepath,
    xml_temp_dir,
    mode="full",
    dry_run=False,
    chapter_title=None,
    maps_path=None,
):
    summary = {"file": os.path.basename(filepath), "changes": [], "errors": []}
    with open(filepath, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    document = data["data"]["document"]
    content = document["content"]
    obj_token = document["document_id"]

    filename = os.path.basename(filepath)
    match = re.match(r"^(.*?)(?:_[a-zA-Z0-9]+)?\.json$", filename)
    chapter_title = chapter_title or (match.group(1) if match else filename)
    maps = load_mermaid_maps(maps_path)
    chapter_key = find_mermaid_key(chapter_title, maps)
    soup = BeautifulSoup(content, "html.parser")

    if mode in ("full", "polish"):
        if transforms.digitize_scorecard(soup):
            summary["changes"].append("scorecard_digitized")
        for tag in soup.find_all(["span", "b"]):
            if tag.has_attr("text-color") and tag["text-color"] in (
                transforms.RED,
                "red",
            ):
                if transforms.should_strip_red(tag):
                    if tag.name == "span":
                        tag.unwrap()
                    else:
                        del tag["text-color"]
        transforms.clean_punctuation(soup)
        if transforms.remove_redundant_h1(soup):
            summary["changes"].append("h1_removed")
        if transforms.reposition_title_emoji(soup):
            summary["changes"].append("title_emoji_front")
        if transforms.reposition_h2_emoji(soup):
            summary["changes"].append("h2_emoji_back")

    had_whiteboards = bool(soup.find_all("whiteboard"))
    whiteboard_mermaids = whiteboards.process_whiteboards(soup, maps, chapter_key)
    if whiteboard_mermaids:
        summary["changes"].append("whiteboards:%s" % len(whiteboard_mermaids))
    processed_xml = str(soup)

    if dry_run:
        os.makedirs(PREVIEW_DIR, exist_ok=True)
        preview_path = os.path.join(PREVIEW_DIR, "preview_%s.xml" % obj_token)
        with open(preview_path, "w", encoding="utf-8") as handle:
            handle.write(processed_xml)
        summary["preview"] = preview_path
        summary["dry_run"] = True
        summary["whiteboards"] = len(whiteboard_mermaids)
        return summary

    if mode == "whiteboard" and had_whiteboards:
        _, errors = whiteboards.refresh_existing_whiteboards(
            content, maps, chapter_title
        )
    elif mode == "whiteboard" and not whiteboard_mermaids:
        errors = [
            "no whiteboard was changed; use polish to insert a mapped missing whiteboard"
        ]
    else:
        errors = writer.overwrite_and_render(
            obj_token,
            processed_xml,
            whiteboard_mermaids,
            xml_temp_dir,
            original_xml=content,
            rollback_maps=maps,
            rollback_title=chapter_title,
        )
    summary["errors"] = errors
    summary["whiteboards"] = len(whiteboard_mermaids)
    return summary


def fetch_node_to_cache(obj_token, title, cache_dir):
    obj_token = lark_client.validate_identifier(obj_token, "document identifier")
    os.makedirs(cache_dir, mode=0o700, exist_ok=True)
    safe_title = re.sub(r"[^\w\-.\u4e00-\u9fff]+", "_", title).strip("._")
    safe_title = (safe_title or "document")[:80]
    digest = hashlib.sha256(obj_token.encode("utf-8")).hexdigest()[:12]
    path = os.path.join(cache_dir, "%s_%s.json" % (safe_title, digest))
    output = lark_client.api_fetch(obj_token)
    if output and output.get("ok"):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(output, handle, ensure_ascii=False, indent=2)
        return path
    return None
