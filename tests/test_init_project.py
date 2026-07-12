"""init_project 离线初始化器回归测试。"""

import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "skill"
    / "feishu-wiki-importer-optimizer"
    / "scripts"
    / "init_project.py"
)
SPEC = importlib.util.spec_from_file_location("init_project", MODULE_PATH)
init_project = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(init_project)


class InitProjectTests(unittest.TestCase):
    def test_creates_complete_private_skeleton_with_secure_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "private-workspace"
            rc = init_project.main(
                ["--workspace", str(workspace), "--project", "demo-project"]
            )
            self.assertEqual(rc, 0)
            project = workspace / "projects" / "demo-project"
            expected_dirs = [workspace, workspace / "archives", project]
            expected_dirs += [project / path for path in init_project.PROJECT_DIRECTORIES]
            for path in expected_dirs:
                self.assertTrue(path.is_dir(), path)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700, path)

            expected_files = [
                workspace / "workspace.json",
                project / "project.json",
                project / "config" / "outline.json",
                project / "generated" / "mermaid_maps.json",
                project / "state" / "remote_nodes.json",
                project / "state" / "uploaded_images.json",
            ]
            for path in expected_files:
                self.assertTrue(path.is_file(), path)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path)
                json.loads(path.read_text(encoding="utf-8"))

            workspace_data = json.loads(
                (workspace / "workspace.json").read_text(encoding="utf-8")
            )
            project_data = json.loads(
                (project / "project.json").read_text(encoding="utf-8")
            )
            self.assertEqual(workspace_data["default_project"], "demo-project")
            self.assertEqual(project_data["project_id"], "demo-project")

    def test_defaults_to_default_project_and_env_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "from-env"
            with patch.dict(
                os.environ, {"FEISHU_WIKI_WORKSPACE": str(workspace)}, clear=False
            ):
                rc = init_project.main([])
            self.assertEqual(rc, 0)
            self.assertTrue((workspace / "projects" / "default").is_dir())

    def test_existing_workspace_default_project_is_used(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "workspace"
            workspace.mkdir()
            config = {"schema_version": 1, "default_project": "selected-project"}
            (workspace / "workspace.json").write_text(
                json.dumps(config), encoding="utf-8"
            )
            rc = init_project.main(["--workspace", str(workspace)])
            self.assertEqual(rc, 0)
            self.assertTrue((workspace / "projects" / "selected-project").is_dir())
            self.assertEqual(
                json.loads((workspace / "workspace.json").read_text(encoding="utf-8")),
                config,
            )

    def test_rejects_unsafe_slugs_and_workspace_locations(self):
        invalid = ["../escape", "a/b", "Upper", "has space", "-start", "end-"]
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            for pos, slug in enumerate(invalid):
                workspace = base / ("workspace-%d" % pos)
                rc = init_project.main(
                    ["--workspace", str(workspace), "--project=" + slug]
                )
                self.assertEqual(rc, 2, slug)
                self.assertFalse(workspace.exists(), slug)
            self.assertFalse((base / "escape").exists())

        rc = init_project.main(
            [
                "--workspace",
                str(ROOT / "should-not-exist"),
                "--project",
                "default",
            ]
        )
        self.assertEqual(rc, 2)
        self.assertFalse((ROOT / "should-not-exist").exists())

    def test_existing_project_is_untouched_without_force(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "workspace"
            self.assertEqual(
                init_project.main(
                    ["--workspace", str(workspace), "--project", "demo"]
                ),
                0,
            )
            outline = workspace / "projects" / "demo" / "config" / "outline.json"
            marker = b'{"custom": true}\n'
            outline.write_bytes(marker)
            before = {
                path: path.read_bytes()
                for path in (workspace / "projects" / "demo").rglob("*.json")
            }

            rc = init_project.main(
                ["--workspace", str(workspace), "--project", "demo"]
            )
            self.assertEqual(rc, 2)
            self.assertEqual(outline.read_bytes(), marker)
            self.assertEqual(
                {path: path.read_bytes() for path in before},
                before,
            )

    def test_force_backs_up_known_files_and_preserves_unknown_files(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "workspace"
            args = ["--workspace", str(workspace), "--project", "demo"]
            self.assertEqual(init_project.main(args), 0)
            project = workspace / "projects" / "demo"
            outline = project / "config" / "outline.json"
            original = b'{"private": "old"}\n'
            outline.write_bytes(original)
            unknown = project / "source" / "chapters" / "keep.md"
            unknown.write_text("keep", encoding="utf-8")

            self.assertEqual(init_project.main(args + ["--force"]), 0)
            self.assertEqual(unknown.read_text(encoding="utf-8"), "keep")
            self.assertEqual(
                json.loads(outline.read_text(encoding="utf-8")),
                {"schema_version": 1, "chapters": []},
            )
            backups = list(
                (workspace / "archives" / "init-project").glob(
                    "*/projects/demo/config/outline.json"
                )
            )
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)
            self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o600)

    def test_templates_and_schemas_are_valid_json(self):
        assets = MODULE_PATH.parents[1] / "assets"
        references = MODULE_PATH.parents[1] / "references"
        template_names = {
            "workspace.template.json",
            "project.template.json",
            "outline.template.json",
            "remote_nodes.template.json",
            "mermaid_maps.template.json",
            "uploaded_images.template.json",
        }
        schema_names = {
            "workspace.schema.json",
            "project.schema.json",
            "outline.schema.json",
            "remote-nodes.schema.json",
        }
        for name in template_names:
            data = json.loads((assets / name).read_text(encoding="utf-8"))
            self.assertIsInstance(data, dict)
        for name in schema_names:
            data = json.loads((references / name).read_text(encoding="utf-8"))
            self.assertEqual(
                data["$schema"], "https://json-schema.org/draft/2020-12/schema"
            )
            self.assertEqual(data["type"], "object")


if __name__ == "__main__":
    unittest.main()
