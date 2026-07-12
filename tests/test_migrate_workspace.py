"""旧私有工作区离线迁移器回归测试。"""

import importlib.util
import json
import stat
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "skill"
    / "feishu-wiki-importer-optimizer"
    / "scripts"
    / "migrate_workspace.py"
)
SPEC = importlib.util.spec_from_file_location("migrate_workspace", MODULE_PATH)
migrate_workspace = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(migrate_workspace)


class MigrateWorkspaceTests(unittest.TestCase):
    def _legacy_workspace(self, root: Path) -> Path:
        workspace = root / "private-workspace"
        for directory in (
            "chapters",
            "temp_images",
            "scratch",
            "mappings",
            "runtime_backups",
            "previews",
            "cache",
            "verification",
            "legacy-archive",
            ".venv/bin",
        ):
            (workspace / directory).mkdir(parents=True, exist_ok=True)
        (workspace / "chapters" / "01-a.md").write_text("source", encoding="utf-8")
        (workspace / "temp_images" / "image.png").write_bytes(b"image")
        (workspace / "scratch" / "chapter_0.json").write_text(
            json.dumps({"xml": "<title>A</title>"}), encoding="utf-8"
        )
        (workspace / "scratch" / "write_jsons.py").write_text(
            "raise SystemExit('archive only')\n", encoding="utf-8"
        )
        (workspace / "runtime_backups" / "snapshot.xml").write_text(
            "<title>old</title>", encoding="utf-8"
        )
        mapping = [
            {
                "index": 0,
                "title": "A",
                "filename": "01-a.md",
                "filepath": "chapters/01-a.md",
                "node_token": "node_synthetic",
                "obj_token": "obj_synthetic",
            }
        ]
        (workspace / "mappings" / "chapters_nodes.json").write_text(
            json.dumps(mapping), encoding="utf-8"
        )
        (workspace / "mappings" / "mermaid_maps.json").write_text(
            json.dumps({"A": "graph TD\nA-->B"}), encoding="utf-8"
        )
        executable = workspace / ".venv" / "bin" / "python"
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(0o755)
        return workspace

    def test_dry_run_does_not_create_project(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._legacy_workspace(Path(temp))
            result = migrate_workspace.migrate(workspace, "default", apply=False)
            self.assertFalse((workspace / "workspace.json").exists())
            self.assertFalse((workspace / "projects").exists())
            self.assertEqual(result["chapters"], 1)
            self.assertEqual(result["prepared_verified"], 1)

    def test_apply_splits_state_archives_legacy_and_preserves_venv_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._legacy_workspace(Path(temp))
            result = migrate_workspace.migrate(workspace, "default", apply=True)
            project = workspace / "projects" / "default"
            outline = json.loads(
                (project / "config" / "outline.json").read_text(encoding="utf-8")
            )
            remote = json.loads(
                (project / "state" / "remote_nodes.json").read_text(encoding="utf-8")
            )
            maps = json.loads(
                (project / "generated" / "mermaid_maps.json").read_text(encoding="utf-8")
            )
            self.assertEqual(outline["chapters"][0]["chapter_id"], "chapter-001")
            self.assertEqual(outline["chapters"][0]["source_path"], "chapters/01-a.md")
            self.assertEqual(remote["nodes"]["chapter-001"]["obj_token"], "obj_synthetic")
            self.assertEqual(maps, {"chapter-001": "graph TD\nA-->B"})
            self.assertTrue((project / "source" / "chapters" / "01-a.md").is_file())
            self.assertTrue((project / "generated" / "prepared" / "chapter_0.json").is_file())
            self.assertFalse((project / "generated" / "prepared" / "write_jsons.py").exists())
            self.assertFalse((workspace / "chapters").exists())
            self.assertFalse((workspace / "mappings").exists())

            report_dir = Path(result["migration"])
            self.assertTrue(
                (report_dir / "legacy-layout" / "scratch" / "write_jsons.py").is_file()
            )
            report = json.loads(
                (report_dir / "migration-report.json").read_text(encoding="utf-8")
            )
            self.assertGreater(report["copied_file_count"], 0)
            self.assertTrue(
                all(not Path(item["destination"]).is_absolute() for item in report["files"])
            )

            executable = workspace / ".venv" / "bin" / "python"
            self.assertEqual(stat.S_IMODE(executable.stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE(project.stat().st_mode), 0o700)
            self.assertEqual(
                stat.S_IMODE((project / "config" / "outline.json").stat().st_mode),
                0o600,
            )

    def test_refuses_unmatched_mermaid_key_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._legacy_workspace(Path(temp))
            (workspace / "mappings" / "mermaid_maps.json").write_text(
                json.dumps({"unknown": "graph TD"}), encoding="utf-8"
            )
            with self.assertRaises(migrate_workspace.MigrationError):
                migrate_workspace.migrate(workspace, "default", apply=True)
            self.assertFalse((workspace / "workspace.json").exists())

    def test_unbound_prepared_json_stays_in_legacy_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = self._legacy_workspace(Path(temp))
            (workspace / "scratch" / "chapter_0.json").write_text(
                json.dumps({"xml": "<title>其他内容</title>"}), encoding="utf-8"
            )
            result = migrate_workspace.migrate(workspace, "default", apply=True)
            self.assertEqual(result["prepared_verified"], 0)
            self.assertFalse(
                (workspace / "projects/default/generated/prepared/chapter_0.json").exists()
            )
            self.assertTrue(
                (
                    Path(result["migration"])
                    / "legacy-layout/scratch/chapter_0.json"
                ).is_file()
            )


if __name__ == "__main__":
    unittest.main()
