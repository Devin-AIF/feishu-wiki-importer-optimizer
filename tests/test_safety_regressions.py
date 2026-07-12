"""离线回归测试：不访问飞书、不调用 lark-cli。

运行：.venv/bin/python -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

# 测试直接加载可发布 Skill 中的正式实现。根目录同名文件只是
# 迁移期兼容入口，不得成为测试通过所依赖的第二套代码。
ROOT = Path(__file__).resolve().parents[1]
FORMAL_SCRIPTS = (
    ROOT / "skill" / "feishu-wiki-importer-optimizer" / "scripts"
).resolve()
sys.path.insert(0, str(FORMAL_SCRIPTS))

import common
import feishu_doc_tools as tools
import feishu_prepare_chapters as prepare
import feishu_push_chapters as push


class MarkdownSafetyTests(unittest.TestCase):
    def test_parenthesized_text_and_link_are_not_dropped(self):
        with tempfile.TemporaryDirectory() as temp:
            rendered = prepare.md_to_html(
                "ordinary sentence (example)\n[x](https://example.com/a)",
                temp, {}, os.path.join(temp, "cache.json"),
            )
        self.assertIn("ordinary sentence (example)", rendered)
        self.assertIn("https://example.com/a", rendered)

    def test_untrusted_html_is_escaped_but_generated_formatting_remains(self):
        rendered = prepare.process_paragraph(
            '<whiteboard type="mermaid">evil</whiteboard> **bold** \\(x+y\\) [^1]'
        )
        self.assertIn("&lt;whiteboard", rendered)
        self.assertIn('<span text-color="rgb(216,57,49)">bold</span>', rendered)
        self.assertIn("<latex>x+y</latex>", rendered)

    def test_image_line_still_uploads(self):
        with tempfile.TemporaryDirectory() as temp:
            os.makedirs(os.path.join(temp, "images"))
            Path(os.path.join(temp, "images", "a.png")).write_bytes(b"not-a-real-image")
            with patch.object(prepare, "upload_image", return_value="file_1") as upload:
                rendered = prepare.md_to_html(
                    "![caption](images/a.png)", temp, {}, os.path.join(temp, "cache.json")
                )
        upload.assert_called_once()
        self.assertIn('src="file_1"', rendered)
        self.assertIn('caption="caption"', rendered)

    def test_image_path_cannot_escape_or_be_remote(self):
        with tempfile.TemporaryDirectory() as temp:
            for image in ("../secret.png", "https://example.com/x.png", "/tmp/x.png"):
                with self.assertRaises(ValueError):
                    prepare._resolve_local_image_path(image, temp)


class TransformSafetyTests(unittest.TestCase):
    def test_h1_only_removed_when_matching_title_and_first_content(self):
        same = BeautifulSoup("<title>同题</title><h1>同题</h1><p>x</p>", "html.parser")
        different = BeautifulSoup("<title>同题</title><h1>不同题</h1><p>x</p>", "html.parser")
        self.assertTrue(common.remove_redundant_h1(same))
        self.assertFalse(common.remove_redundant_h1(different))
        self.assertIsNotNone(different.find("h1"))

    def test_emoji_and_score_distribution(self):
        self.assertTrue(common.EMOJI_PATTERN.search("📘"))
        self.assertTrue(common.EMOJI_PATTERN.search("⚠️"))
        scores = common.distribute_scores(9.0, [5, 0, 0, 0])
        self.assertAlmostEqual(sum(scores) / 4, 9.0)

    def test_existing_whiteboards_are_preserved_by_transform(self):
        soup = BeautifulSoup('<whiteboard token="wb1" type="mermaid"></whiteboard>', "html.parser")
        self.assertEqual(common.process_whiteboards(soup, {"章节": "graph TD"}, "章节"), ["graph TD"])
        self.assertNotIn("token", soup.whiteboard.attrs)

    def test_existing_whiteboard_without_source_refuses_overwrite(self):
        soup = BeautifulSoup('<whiteboard token="wb1" type="mermaid"></whiteboard>', "html.parser")
        with self.assertRaises(common.WhiteboardSourceError):
            common.process_whiteboards(soup, {}, "章节")

    def test_navigation_can_hydrate_existing_whiteboard_from_map(self):
        xml, codes = common.prepare_document_whiteboards_for_overwrite(
            '<title>章节</title><whiteboard token="wb1" type="mermaid"></whiteboard>',
            maps={"章节": "graph TD"},
        )
        self.assertEqual(codes, ["graph TD"])
        self.assertNotIn("token", xml)

    def test_restore_existing_whiteboard_uses_embedded_source_without_map(self):
        content = '<title>章节</title><whiteboard token="wb1" type="mermaid">graph LR</whiteboard>'
        with patch.object(common, "api_update_whiteboard", return_value={"ok": True}) as update:
            _, errors = common.refresh_existing_whiteboards(content, {}, "章节")
        self.assertEqual(errors, [])
        update.assert_called_once_with("wb1", "graph LR")


class WriterSafetyTests(unittest.TestCase):
    def test_tests_load_formal_skill_implementations(self):
        for module in (common, tools, prepare, push):
            self.assertEqual(Path(module.__file__).resolve().parent, FORMAL_SCRIPTS)

    def test_runtime_data_is_outside_publishable_skill(self):
        skill_dir = Path(common.SKILL_DIR).resolve()
        runtime_dir = Path(common.RUNTIME_DIR).resolve()
        self.assertNotEqual(runtime_dir, skill_dir)
        self.assertNotIn(skill_dir, runtime_dir.parents)
        self.assertEqual(Path(common.DEFAULT_MAPPING_PATH).parent, runtime_dir / "mappings")
        self.assertEqual(Path(common.MERMAID_MAPS_PATH).parent, runtime_dir / "mappings")

    def test_lark_identifiers_reject_cli_option_shaped_values(self):
        self.assertEqual(common.validate_identifier("Abc_123-xyz"), "Abc_123-xyz")
        for invalid in ("", "--as", "a space", "a/b", "a\n"):
            with self.assertRaises(ValueError):
                common.validate_identifier(invalid)

    def test_writer_keeps_errors_list_contract_and_rolls_back(self):
        original = '<title>旧</title><whiteboard token="old-wb" type="mermaid">graph TD</whiteboard>'
        calls = []

        def fake_once(obj, xml, codes, directory):
            calls.append((xml, list(codes)))
            return (["whiteboard failed"], True) if len(calls) == 1 else ([], True)

        with tempfile.TemporaryDirectory() as temp, patch.object(common, "_overwrite_once", side_effect=fake_once):
            errors = common.overwrite_and_render("doc1", "<title>新</title>", [], temp, original_xml=original)
        self.assertIsInstance(errors, list)
        self.assertIn("original document was restored", " ".join(errors))
        self.assertEqual(len(calls), 2)

    def test_writer_refuses_when_original_whiteboard_cannot_be_restored(self):
        original = '<title>旧</title><whiteboard token="old-wb" type="mermaid"></whiteboard>'
        with tempfile.TemporaryDirectory() as temp, patch.object(common, "_overwrite_once") as write:
            errors = common.overwrite_and_render("doc1", "<title>新</title>", [], temp, original_xml=original)
        self.assertIn("cannot be restored safely", " ".join(errors))
        write.assert_not_called()

    def test_page_overwrite_does_not_retry(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(common, "run_cmd", side_effect=RuntimeError("timeout")) as run:
            errors, overwritten = common._overwrite_once("doc1", "<title>x</title>", [], temp)
        self.assertFalse(overwritten)
        self.assertEqual(len(errors), 1)
        self.assertEqual(run.call_args.kwargs["retries"], 1)

    def test_writer_accepts_mapped_original_whiteboard_for_rollback(self):
        original = '<title>章节</title><whiteboard token="old-wb" type="mermaid"></whiteboard>'
        calls = []

        def fake_once(obj, xml, codes, directory):
            calls.append((xml, list(codes)))
            return (["render failed"], True) if len(calls) == 1 else ([], True)

        with tempfile.TemporaryDirectory() as temp, patch.object(common, "_overwrite_once", side_effect=fake_once):
            errors = common.overwrite_and_render(
                "doc1", "<title>新</title>", [], temp, original_xml=original,
                rollback_maps={"章节": "graph TD"}, rollback_title="章节",
            )
        self.assertIn("original document was restored", " ".join(errors))
        self.assertEqual(calls[1][1], ["graph TD"])

    def test_create_nodes_fails_closed_before_any_create_or_write(self):
        mapping = [{"index": 0, "title": "A"}]
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "mapping.json")
            Path(path).write_text(json.dumps(mapping), encoding="utf-8")
            parser = tools.build_parser()
            args = parser.parse_args(["create-nodes", "--mapping", path, "--space", "s", "--parent", "p"])
            with patch.object(tools, "api_get_nodes", side_effect=common.NodeScanError("offline")), \
                 patch.object(tools, "api_create_node") as create:
                with self.assertRaises(SystemExit) as exited:
                    tools.cmd_create_nodes(args)
            self.assertEqual(exited.exception.code, 2)
            create.assert_not_called()
            self.assertEqual(Path(path).read_text(encoding="utf-8"), json.dumps(mapping))

    def test_navigation_xml_escapes_values(self):
        xml = tools._build_sub_page_xml(
            [{"index": 0, "title": 'A " < B', "obj_token": "id&1"}], "space&", "node\""
        )
        self.assertIn("space&amp;", xml)
        self.assertIn("id&amp;1", xml)
        self.assertIn("A &quot; &lt; B", xml)


class PushSafetyTests(unittest.TestCase):
    def test_push_plan_is_generic_and_supports_legacy_chapter_index(self):
        with tempfile.TemporaryDirectory() as temp:
            mapping = [
                {"index": 1, "filename": "01-test.md", "title": "章节", "obj_token": "obj"},
                {"index": 50, "filename": "50-总纲.md", "title": "总纲", "obj_token": "overview"},
            ]
            Path(os.path.join(temp, "chapter_0.json")).write_text(
                json.dumps({"xml": "<title>章节</title>", "mermaid": "graph TD"}), encoding="utf-8"
            )
            plan, warnings = push.build_push_plan(mapping, temp)
        self.assertEqual(len(plan), 1)
        self.assertFalse(plan[0]["is_overview"])
        self.assertTrue(any("缺少" in warning for warning in warnings))

    def test_push_dry_run_never_calls_writer(self):
        with tempfile.TemporaryDirectory() as temp:
            mapping_path = os.path.join(temp, "mapping.json")
            maps_path = os.path.join(temp, "maps.json")
            Path(mapping_path).write_text(
                json.dumps([{"index": 1, "filename": "01-test.md", "title": "章节", "obj_token": "obj"}]),
                encoding="utf-8",
            )
            Path(os.path.join(temp, "chapter_0.json")).write_text(
                json.dumps({"xml": "<title>章节</title>"}), encoding="utf-8"
            )
            with patch.object(push, "overwrite_and_render") as writer:
                rc = push.main(["--json-dir", temp, "--chapters-nodes", mapping_path, "--maps-file", maps_path, "--dry-run"])
        self.assertEqual(rc, 0)
        writer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
