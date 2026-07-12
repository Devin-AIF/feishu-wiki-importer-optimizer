#!/usr/bin/env python3
"""飞书知识库导入、导航、排版和白板修复的唯一主 CLI。"""

import sys
from pathlib import Path


SCRIPT_DIR = str(Path(__file__).resolve().parent)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from feishu_wiki.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
