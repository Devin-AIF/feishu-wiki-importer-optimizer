#!/usr/bin/env python3
"""已弃用的章节推送 CLI；正式入口为 `feishu_wiki.py push`。"""

import sys

from feishu_wiki.push import (
    _chapter_index,
    _is_overview,
    _json_path_for_item,
    _load_json,
    _validate_payload,
    build_push_plan,
    update_maps_file,
)
from feishu_wiki import push as _implementation
from feishu_wiki.writer import overwrite_and_render


def main(argv=None):
    return _implementation.main(argv)


if __name__ == "__main__":
    sys.stderr.write(
        "[DEPRECATED] feishu_push_chapters.py 仅供旧自动化兼容；"
        "请使用 scripts/feishu_wiki.py push。\n"
    )
    raise SystemExit(main())
