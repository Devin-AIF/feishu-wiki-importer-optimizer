"""发布包边界测试：只验证本地 allowlist，不访问飞书或网络。"""

import importlib.util
import tempfile
import unittest
import zipfile
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

    def test_release_includes_initializer_schemas_and_templates(self):
        expected = {
            Path("scripts/init_project.py"),
            Path("scripts/migrate_workspace.py"),
            Path("scripts/feishu_wiki.py"),
            Path("scripts/feishu_wiki/cli.py"),
            Path("scripts/feishu_wiki/lark_client.py"),
            Path("scripts/feishu_wiki/paths.py"),
            Path("scripts/feishu_wiki/prepare.py"),
            Path("scripts/feishu_wiki/push.py"),
            Path("scripts/feishu_wiki/service.py"),
            Path("scripts/feishu_wiki/storage.py"),
            Path("scripts/feishu_wiki/transforms.py"),
            Path("scripts/feishu_wiki/whiteboards.py"),
            Path("scripts/feishu_wiki/writer.py"),
            Path("references/project-layout.md"),
            Path("references/workspace.schema.json"),
            Path("references/project.schema.json"),
            Path("references/outline.schema.json"),
            Path("references/remote-nodes.schema.json"),
            Path("assets/workspace.template.json"),
            Path("assets/project.template.json"),
            Path("assets/outline.template.json"),
            Path("assets/outline.example.json"),
            Path("assets/legacy_chapters_nodes.example.json"),
            Path("assets/remote_nodes.template.json"),
            Path("assets/mermaid_maps.template.json"),
            Path("assets/uploaded_images.template.json"),
        }
        self.assertTrue(expected.issubset(set(build_release.ALLOWED_PATHS)))

    def test_zip_contains_exact_allowlist(self):
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp) / "stage"
            destination = Path(temp) / "release.zip"
            build_release.copy_allowlist(stage)
            build_release.zip_stage(stage, destination)
            with zipfile.ZipFile(destination) as archive:
                actual = {Path(name) for name in archive.namelist()}
        expected = {
            Path(build_release.SKILL_NAME) / path
            for path in build_release.ALLOWED_PATHS
        }
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
