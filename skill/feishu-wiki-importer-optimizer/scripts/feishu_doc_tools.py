#!/usr/bin/env python3
"""已弃用的正式 CLI 别名；新命令请使用 `feishu_wiki.py`。"""

import sys
from pathlib import Path


SCRIPT_DIR = str(Path(__file__).resolve().parent)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from feishu_wiki.cli import (
    build_parser,
    build_sub_page_xml as _build_sub_page_xml,
    cmd_create_nodes,
    cmd_polish,
    cmd_restore_wb,
    cmd_update_nav,
    cmd_prepare,
    cmd_push,
    main,
    process_one as _process_one,
    run_batch as _run_batch,
)
from feishu_wiki.lark_client import (
    NodeScanError,
    api_create_node,
    api_fetch,
    api_get_nodes,
)


if __name__ == "__main__":
    sys.stderr.write(
        "[DEPRECATED] feishu_doc_tools.py 将在迁移完成后删除；"
        "请使用 scripts/feishu_wiki.py。\n"
    )
    raise SystemExit(main())
