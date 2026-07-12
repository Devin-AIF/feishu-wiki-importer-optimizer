"""兼容入口：实现已迁移到可发布 Skill 的 ``scripts/common.py``。

保留此模块，避免已有自动化、测试或个人脚本因目录分层而失效。新代码应从
``skill/feishu-wiki-importer-optimizer/scripts`` 导入，或通过根目录 CLI 入口调用。
"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


_IMPL = Path(__file__).parent / "skill" / "feishu-wiki-importer-optimizer" / "scripts" / "common.py"
_SCRIPTS = str(_IMPL.parent)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
_SPEC = spec_from_file_location(__name__, _IMPL)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - installation corruption
    raise ImportError(f"Cannot load Skill implementation: {_IMPL}")
_MODULE = module_from_spec(_SPEC)
sys.modules[__name__] = _MODULE
_SPEC.loader.exec_module(_MODULE)
