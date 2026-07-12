"""发布包边界测试：只验证本地 allowlist，不访问飞书或网络。"""

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "build_release.py"
SPEC = importlib.util.spec_from_file_location("build_release", MODULE_PATH)
build_release = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(build_release)


class ReleasePackageTests(unittest.TestCase):
    def test_allowlist_stage_is_clean(self):
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp) / "stage"
            copied = build_release.copy_allowlist(stage)
            self.assertEqual(len(copied), len(build_release.ALLOWED_PATHS))
            self.assertEqual(build_release.scan_stage(stage), [])

    def test_scanner_rejects_private_mapping(self):
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp) / "stage"
            build_release.copy_allowlist(stage)
            forbidden = stage / build_release.SKILL_NAME / "assets" / "chapters_nodes.json"
            forbidden.write_text('[{"node_token":"sensitive"}]', encoding="utf-8")
            problems = build_release.scan_stage(stage)
        self.assertTrue(any("forbidden filename" in item for item in problems))
        self.assertTrue(any("non-example JSON" in item for item in problems))


if __name__ == "__main__":
    unittest.main()
