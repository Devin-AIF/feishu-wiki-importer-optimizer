"""单一正式入口与 Skill 内兼容层回归测试。"""

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

    def test_repository_root_has_no_duplicate_runtime_entrypoints(self):
        retired = {
            "common.py",
            "feishu_doc_tools.py",
            "feishu_prepare_chapters.py",
            "feishu_push_chapters.py",
            "setup.sh",
            "doctor.sh",
            "requirements.txt",
        }
        self.assertEqual([name for name in sorted(retired) if (ROOT / name).exists()], [])

    def test_unified_cli_is_the_only_non_deprecated_python_entrypoint(self):
        cli = FORMAL_SCRIPTS / "feishu_wiki.py"
        result = self._run(cli, "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("[DEPRECATED]", result.stderr)
        self.assertIn("飞书知识库文献排版打磨与建档统一工具", result.stdout)
        self.assertIn("--workspace", result.stdout)
        self.assertIn("--project", result.stdout)

    def test_formal_common_import_keeps_legacy_api(self):
        code = (
            "import pathlib, common; "
            "assert hasattr(common, 'resolve_mapping'); "
            "assert hasattr(common, 'save_mapping_state'); "
            "print(pathlib.Path(common.__file__).resolve())"
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = str(FORMAL_SCRIPTS)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(Path(result.stdout.strip()), FORMAL_SCRIPTS / "common.py")

    def test_formal_aliases_are_thin_and_deprecated_when_executed(self):
        aliases = [
            FORMAL_SCRIPTS / "feishu_doc_tools.py",
            FORMAL_SCRIPTS / "feishu_prepare_chapters.py",
            FORMAL_SCRIPTS / "feishu_push_chapters.py",
        ]
        for alias in aliases:
            with self.subTest(alias=alias.name):
                result = self._run(alias, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr.count("[DEPRECATED]"), 1)
                self.assertLess(len(alias.read_text(encoding="utf-8").splitlines()), 50)


if __name__ == "__main__":
    unittest.main()
