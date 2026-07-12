"""Mermaid 白板源码水化、局部重绘和覆写前安全准备。"""

import sys

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.stderr.write("\n[ERROR] 缺少依赖 beautifulsoup4。\n\n")
    sys.exit(2)

from . import lark_client
from .storage import find_mermaid_key


class WhiteboardSourceError(RuntimeError):
    """覆写前无法为现有白板找到可渲染的 Mermaid 源码。"""


def process_whiteboards(soup, maps, chapter_key):
    codes = []
    whiteboards = soup.find_all("whiteboard")
    if whiteboards:
        return _hydrate_existing_whiteboards(whiteboards, maps, chapter_key)

    mindmap_tokens = (
        "逻辑图示", "思维全景图", "全景图", "逻辑脑图", "思维导图", "脑图",
    )
    target = None
    for heading in soup.find_all("h2"):
        if any(token in heading.get_text() for token in mindmap_tokens):
            target = heading
            break
    if target is None:
        print(
            "[WARN] 未检测到 <whiteboard> 也未找到含脑图标题（%s）的 <h2>："
            "若此页为文章页(Leaf)/总纲页(Overview)，将缺少强制 Mermaid 脑图。"
            % "/".join(mindmap_tokens)
        )
        return codes
    if chapter_key and chapter_key in maps:
        code = maps[chapter_key]
        codes.append(code)
        whiteboard = soup.new_tag("whiteboard", attrs={"type": "mermaid"})
        whiteboard.string = code
        target.insert_after(whiteboard)
    else:
        print(
            "[WARN] 页面含『%s』标题，但 mermaid_maps.json 中无『%s』对应脑图："
            "该页将无脑图。请补充 mermaid_maps.json 条目（键须与页面标题精确匹配）。"
            % (target.get_text(strip=True), chapter_key or "<未知标题>")
        )
    return codes


def _hydrate_existing_whiteboards(whiteboards, maps, chapter_key):
    raw_codes = [whiteboard.get_text().strip() for whiteboard in whiteboards]
    missing = [index for index, code in enumerate(raw_codes) if not code]
    mapped_code = maps.get(chapter_key) if chapter_key else None
    if missing:
        if len(whiteboards) == 1 and isinstance(mapped_code, str) and mapped_code.strip():
            raw_codes = [mapped_code]
        else:
            raise WhiteboardSourceError(
                "existing whiteboard source is unavailable; provide a matching Mermaid map "
                "for this single-page whiteboard before overwrite"
            )
    for whiteboard, code in zip(whiteboards, raw_codes):
        for attribute in ("id", "token", "block-token", "block_token"):
            whiteboard.attrs.pop(attribute, None)
        whiteboard.string = code
    return raw_codes


def prepare_document_whiteboards_for_overwrite(
    content, maps=None, chapter_title=None
):
    soup = BeautifulSoup(content or "", "html.parser")
    whiteboards = soup.find_all("whiteboard")
    if not whiteboards:
        return str(soup), []
    if not chapter_title:
        title = soup.find("title")
        chapter_title = title.get_text().strip() if title else None
    maps = maps or {}
    chapter_key = find_mermaid_key(chapter_title, maps)
    codes = _hydrate_existing_whiteboards(whiteboards, maps, chapter_key)
    return str(soup), codes


def refresh_existing_whiteboards(content, maps, chapter_title, dry_run=False):
    soup = BeautifulSoup(content or "", "html.parser")
    whiteboards = soup.find_all("whiteboard")
    if not whiteboards:
        return [], ["no existing whiteboard; use polish to insert a missing one"]
    key = find_mermaid_key(chapter_title, maps)
    raw_codes = [whiteboard.get_text().strip() for whiteboard in whiteboards]
    if key:
        codes = [maps[key]] * len(whiteboards)
    elif all(raw_codes):
        codes = raw_codes
    else:
        return [], [
            "no Mermaid source for %r; existing whiteboard was preserved"
            % chapter_title
        ]
    tokens = [
        whiteboard.get("token")
        or whiteboard.get("id")
        or whiteboard.get("block-token")
        or whiteboard.get("block_token")
        for whiteboard in whiteboards
    ]
    if any(not token for token in tokens):
        return [], ["existing whiteboard is missing token/id; preserved without overwrite"]
    if dry_run:
        source = repr(key) if key else "embedded Mermaid source"
        return [
            "would refresh %s whiteboard(s) using %s" % (len(tokens), source)
        ], []
    errors = []
    for token, code in zip(tokens, codes):
        result = lark_client.api_update_whiteboard(token, code)
        if not result.get("ok"):
            errors.append("whiteboard %s: %s" % (token, result.get("error")))
    return [], errors


def extract_existing_whiteboards(content):
    soup = BeautifulSoup(content or "", "html.parser")
    codes = []
    for whiteboard in soup.find_all("whiteboard"):
        code = whiteboard.get_text().strip()
        codes.append(code)
        for attribute in ("id", "token"):
            whiteboard.attrs.pop(attribute, None)
        whiteboard.string = code
    return str(soup), codes


def can_restore_original_whiteboards(content, maps=None, chapter_title=None):
    soup = BeautifulSoup(content or "", "html.parser")
    whiteboards = soup.find_all("whiteboard")
    if all(whiteboard.get_text().strip() for whiteboard in whiteboards):
        return True
    if not whiteboards:
        return True
    maps = maps or {}
    if not chapter_title:
        title = soup.find("title")
        chapter_title = title.get_text().strip() if title else None
    key = find_mermaid_key(chapter_title, maps)
    return len(whiteboards) == 1 and bool(key and maps.get(key))
