"""根目录兼容入口的退役期测试。

业务回归测试只加载正式 Skill 代码；本文件只确认旧入口仍可转发且
会给出明确的弃用提示。
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORMAL_SCRIPTS = (
    ROOT / "skill" / "feishu-wiki-importer-optimizer" / "scripts"
).resolve()


class CompatibilityEntrypointTests(unittest.TestCase):
    def _run(self, *args):
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, *map(str, args)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def test_root_unified_cli_forwards_with_deprecation_notice(self):
        result = self._run(ROOT / "feishu_doc_tools.py", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[DEPRECATED]", result.stderr)
        self.assertIn("飞书知识库文献排版打磨与建档统一工具", result.stdout)

    def test_root_common_import_forwards_silently_to_formal_source(self):
        code = (
            "import pathlib, common; "
            "print(pathlib.Path(common.__file__).resolve())"
        )
        result = self._run("-c", code)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(Path(result.stdout.strip()), FORMAL_SCRIPTS / "common.py")

    def test_root_cli_import_is_silent(self):
        result = self._run("-c", "import feishu_doc_tools")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
