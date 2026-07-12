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
        self.assertEqual(result.stderr.count("[DEPRECATED]"), 1)
        self.assertIn("飞书知识库文献排版打磨与建档统一工具", result.stdout)

    def test_new_unified_cli_has_no_deprecation_notice(self):
        cli = FORMAL_SCRIPTS / "feishu_wiki.py"
        result = self._run(cli, "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("[DEPRECATED]", result.stderr)
        self.assertIn("prepare", result.stdout)
        self.assertIn("push", result.stdout)

    def test_unified_push_dry_run_exit_code_is_forwarded(self):
        with self.subTest("invalid input returns argparse failure"):
            cli = FORMAL_SCRIPTS / "feishu_wiki.py"
            result = self._run(cli, "push")
            self.assertEqual(result.returncode, 2)

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
        code = (
            "import feishu_doc_tools; "
            "assert hasattr(feishu_doc_tools, 'build_parser'); "
            "assert hasattr(feishu_doc_tools, 'cmd_create_nodes'); "
            "assert hasattr(feishu_doc_tools, 'api_fetch')"
        )
        result = self._run("-c", code)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")

    def test_unified_push_dry_run_is_fully_offline(self):
        import json
        import tempfile

        cli = FORMAL_SCRIPTS / "feishu_wiki.py"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            json_dir = temp / "prepared"
            json_dir.mkdir()
            mapping = temp / "chapters_nodes.json"
            maps = temp / "mermaid_maps.json"
            chapter = json_dir / "chapter_0.json"
            mapping.write_text(
                json.dumps(
                    [
                        {
                            "index": 0,
                            "title": "离线测试章节",
                            "filename": "01-离线测试.md",
                            "obj_token": "synthetic-object-token",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            maps.write_text("{}\n", encoding="utf-8")
            chapter.write_text(
                json.dumps(
                    {"xml": "<title>离线测试</title><p>内容</p>", "mermaid": "graph TD\nA-->B"},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            before = maps.read_bytes()
            env = dict(os.environ)
            env["PATH"] = "/usr/bin:/bin"
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            result = subprocess.run(
                [
                    sys.executable,
                    str(cli),
                    "push",
                    "--json-dir",
                    str(json_dir),
                    "--chapters-nodes",
                    str(mapping),
                    "--maps-file",
                    str(maps),
                    "--dry-run",
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Prepared 1 chapter write(s) [DRY-RUN]", result.stdout)
            self.assertIn("[PLAN] chapter: 离线测试章节", result.stdout)
            self.assertEqual(maps.read_bytes(), before)

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
