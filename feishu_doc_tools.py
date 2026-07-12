#!/usr/bin/env python3
"""已弃用的兼容入口；实际 CLI 位于 Skill 的 ``scripts/`` 目录。"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import runpy
import sys

_SCRIPTS = Path(__file__).parent / "skill" / "feishu-wiki-importer-optimizer" / "scripts"
_MAIN_IMPL = _SCRIPTS / "feishu_wiki.py"
_COMPAT_IMPL = _SCRIPTS / "feishu_doc_tools.py"
if __name__ == "__main__":
    sys.stderr.write(
        "[DEPRECATED] 根目录 feishu_doc_tools.py 将在迁移完成后删除；"
        "请使用 skill/feishu-wiki-importer-optimizer/scripts/feishu_wiki.py。\n"
    )
    runpy.run_path(str(_MAIN_IMPL), run_name="__main__")
else:
    # 保留旧模块的 import API；直接执行时才转发到新主 CLI。
    scripts = str(_SCRIPTS)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = spec_from_file_location(__name__, _COMPAT_IMPL)
    if spec is None or spec.loader is None:  # pragma: no cover - installation corruption
        raise ImportError(f"Cannot load Skill compatibility layer: {_COMPAT_IMPL}")
    module = module_from_spec(spec)
    sys.modules[__name__] = module
    spec.loader.exec_module(module)
