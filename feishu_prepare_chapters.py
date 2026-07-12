#!/usr/bin/env python3
"""兼容入口；实际 CLI 位于 Skill 的 ``scripts/`` 目录。"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import runpy
import sys


_IMPL = Path(__file__).parent / "skill" / "feishu-wiki-importer-optimizer" / "scripts" / "feishu_prepare_chapters.py"
if __name__ == "__main__":
    runpy.run_path(str(_IMPL), run_name="__main__")
else:
    scripts = str(_IMPL.parent)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = spec_from_file_location(__name__, _IMPL)
    if spec is None or spec.loader is None:  # pragma: no cover - installation corruption
        raise ImportError(f"Cannot load Skill implementation: {_IMPL}")
    module = module_from_spec(spec)
    sys.modules[__name__] = module
    spec.loader.exec_module(module)
