"""分层项目路径、新配置和统一 CLI 离线回归测试。"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FORMAL_SCRIPTS = (
    ROOT / "skill" / "feishu-wiki-importer-optimizer" / "scripts"
).resolve()
sys.path.insert(0, str(FORMAL_SCRIPTS))

from feishu_wiki import cli as cli_impl, lark_client, paths, storage


class ProjectLayoutTests(unittest.TestCase):
    def _project(self, root: Path):
        project = root / "projects" / "demo"
        (project / "config").mkdir(parents=True)
        (project / "state").mkdir(parents=True)
        (project / "generated" / "prepared").mkdir(parents=True)
        (project / "source" / "chapters" / "images").mkdir(parents=True)
        (root / "workspace.json").write_text(
            json.dumps({"schema_version": 1, "default_project": "demo"}),
            encoding="utf-8",
        )
        outline = {
            "schema_version": 1,
            "chapters": [
                {
                    "chapter_id": "chapter-001",
                    "index": 0,
                    "title": "章节",
                    "kind": "article",
                    "parent_chapter_id": None,
                    "source_path": "chapters/01-test.md",
                }
            ],
        }
        remote = {
            "schema_version": 1,
            "space_id": None,
            "parent_node_token": None,
            "parent_obj_token": None,
            "nodes": {
                "chapter-001": {
                    "node_token": "node_synthetic",
                    "obj_token": "obj_synthetic",
                    "last_seen_at": None,
                }
            },
        }
        (project / "config" / "outline.json").write_text(
            json.dumps(outline, ensure_ascii=False), encoding="utf-8"
        )
        (project / "state" / "remote_nodes.json").write_text(
            json.dumps(remote), encoding="utf-8"
        )
        (project / "state" / "uploaded_images.json").write_text("{}\n", encoding="utf-8")
        (project / "generated" / "mermaid_maps.json").write_text(
            json.dumps({"chapter-001": "graph TD\nA-->B"}), encoding="utf-8"
        )
        (project / "generated" / "prepared" / "chapter_0.json").write_text(
            json.dumps(
                {
                    "xml": (
                        "<title>章节</title>"
                        "<h2>三、 核心观点解读</h2><ul><li>x</li></ul>"
                        "<h2>五、 行动实践清单</h2><p>old</p>"
                    )
                }
            ),
            encoding="utf-8",
        )
        (project / "source" / "chapters" / "01-test.md").write_text(
            "# 章节\n\n![图](images/a.png)\n",
            encoding="utf-8",
        )
        (project / "source" / "chapters" / "images" / "a.png").write_bytes(
            b"synthetic-image"
        )
        return project

    def test_cli_workspace_and_workspace_json_select_project(self):
        previous = (paths.RUNTIME_DIR, paths.PROJECT)
        try:
            with tempfile.TemporaryDirectory() as temp:
                workspace = Path(temp) / "workspace"
                project = self._project(workspace)
                configured = paths.configure(str(workspace), None)
                self.assertEqual(configured["PROJECT"], "demo")
                self.assertEqual(
                    Path(configured["DEFAULT_MAPPING_PATH"]),
                    project / "config" / "outline.json",
                )
                self.assertEqual(
                    Path(configured["RUNTIME_BACKUP_DIR"]),
                    project / "backups" / "runtime",
                )
        finally:
            paths.configure(*previous)

    def test_outline_and_remote_state_merge_without_exposing_tokens_to_outline(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "workspace"
            project = self._project(workspace)
            outline_path = project / "config" / "outline.json"
            before = outline_path.read_bytes()
            path, mapping = storage.resolve_mapping(str(outline_path))
            self.assertEqual(Path(path), outline_path)
            self.assertEqual(mapping[0]["chapter_id"], "chapter-001")
            self.assertEqual(mapping[0]["obj_token"], "obj_synthetic")
            mapping[0]["obj_token"] = "obj_updated"
            storage.save_mapping_state(path, mapping, space_id="space_synthetic")
            self.assertEqual(outline_path.read_bytes(), before)
            remote = json.loads(
                (project / "state" / "remote_nodes.json").read_text(encoding="utf-8")
            )
            self.assertEqual(remote["nodes"]["chapter-001"]["obj_token"], "obj_updated")
            self.assertEqual(remote["space_id"], "space_synthetic")

    def test_unified_push_uses_project_defaults_and_stays_offline(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "workspace"
            project = self._project(workspace)
            maps_path = project / "generated" / "mermaid_maps.json"
            before = maps_path.read_bytes()
            env = dict(os.environ)
            env["PATH"] = "/usr/bin:/bin"
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["FEISHU_WIKI_WORKSPACE"] = str(ROOT)
            result = subprocess.run(
                [
                    sys.executable,
                    str(FORMAL_SCRIPTS / "feishu_wiki.py"),
                    "--workspace",
                    str(workspace),
                    "push",
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
            self.assertEqual(maps_path.read_bytes(), before)

    def test_chapter_id_mermaid_key_precedes_legacy_title_key(self):
        maps = {"chapter-001": "new", "章节": "legacy"}
        self.assertEqual(
            storage.find_mermaid_key("章节", maps, chapter_id="chapter-001"),
            "chapter-001",
        )

    def test_unified_prepare_dry_run_never_uploads_or_overwrites(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "workspace"
            project = self._project(workspace)
            chapter = project / "generated" / "prepared" / "chapter_0.json"
            cache = project / "state" / "uploaded_images.json"
            before_chapter = chapter.read_bytes()
            before_cache = cache.read_bytes()
            env = dict(os.environ)
            env["PATH"] = "/usr/bin:/bin"
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            result = subprocess.run(
                [
                    sys.executable,
                    str(FORMAL_SCRIPTS / "feishu_wiki.py"),
                    "--workspace",
                    str(workspace),
                    "prepare",
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
            self.assertIn("[DRY-RUN] Preview JSON files generated", result.stdout)
            self.assertEqual(chapter.read_bytes(), before_chapter)
            self.assertEqual(cache.read_bytes(), before_cache)
            self.assertTrue((project / "previews" / "prepare" / "chapter_0.json").is_file())

    def test_runtime_workspace_cannot_be_repository_or_skill_directory(self):
        for unsafe in (ROOT, FORMAL_SCRIPTS.parent):
            with self.subTest(path=unsafe), self.assertRaises(paths.WorkspacePathError):
                paths.configure(str(unsafe), "default")

    def test_update_nav_hydrates_parent_whiteboard_by_chapter_id(self):
        previous = (paths.RUNTIME_DIR, paths.PROJECT)
        try:
            with tempfile.TemporaryDirectory() as temp:
                workspace = Path(temp) / "workspace"
                project = self._project(workspace)
                paths.configure(str(workspace), "demo")
                parser = cli_impl.build_parser()
                args = parser.parse_args(
                    [
                        "update-nav",
                        "--mapping", str(project / "config" / "outline.json"),
                        "--maps", str(project / "generated" / "mermaid_maps.json"),
                        "--space", "space_synthetic",
                        "--parent-obj", "obj_synthetic",
                        "--parent-node", "node_parent_synthetic",
                        "--dry-run",
                    ]
                )
                fetched = {
                    "ok": True,
                    "data": {
                        "document": {
                            "content": (
                                '<title>章节</title>'
                                '<whiteboard token="wb" type="mermaid"></whiteboard>'
                                '<h2>五、 导航</h2>'
                            )
                        }
                    },
                }
                with patch.object(lark_client, "api_fetch", return_value=fetched):
                    self.assertEqual(cli_impl.cmd_update_nav(args), 0)
                preview = project / "previews" / "dryrun_top_node_preview.xml"
                self.assertIn("graph TD", preview.read_text(encoding="utf-8"))
        finally:
            paths.configure(*previous)


if __name__ == "__main__":
    unittest.main()
