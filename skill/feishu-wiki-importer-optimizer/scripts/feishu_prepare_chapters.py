#!/usr/bin/env python3
"""已弃用的章节预处理 CLI；正式入口为 `feishu_wiki.py prepare`。"""

import sys

from feishu_wiki.prepare import (
    _image_cache_key,
    _image_dimensions,
    _resolve_local_image_path,
    _safe_caption,
    _sanitize_review_html,
    load_json_file,
    md_to_html,
    process_paragraph,
    save_json_file,
    update_chapter_json,
    upload_image,
)
from feishu_wiki import prepare as _implementation


def main(argv=None):
    return _implementation.main(argv)


if __name__ == "__main__":
    sys.stderr.write(
        "[DEPRECATED] feishu_prepare_chapters.py 仅供旧自动化兼容；"
        "请使用 scripts/feishu_wiki.py prepare。\n"
    )
    raise SystemExit(main())
