"""带快照、单文档锁与回滚的飞书文档覆写器。"""

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime

from . import lark_client, whiteboards
from .paths import RUNTIME_BACKUP_DIR


def overwrite_once(obj_token, processed_xml, whiteboard_mermaids, xml_temp_dir):
    obj_token = lark_client.validate_identifier(obj_token, "document identifier")
    processed_xml = re.sub(r'\s+id="dox(cn)?[^"]+"', "", processed_xml)
    errors = []
    temp_file = "temp_%s.xml" % obj_token
    temp_path = os.path.join(xml_temp_dir, temp_file)
    os.makedirs(xml_temp_dir, exist_ok=True)
    with open(temp_path, "w", encoding="utf-8") as handle:
        handle.write(processed_xml)
    cmd = [
        "lark-cli", "docs", "+update", "--doc", obj_token,
        "--command", "overwrite", "--content", "@" + temp_file,
        "--format", "json", "--as", "user",
    ]
    overwritten = False
    try:
        output = json.loads(
            lark_client.run_cmd(cmd, cwd=xml_temp_dir, retries=1).stdout
        )
        if output.get("ok"):
            overwritten = True
            blocks = output.get("data", {}).get("document", {}).get("new_blocks", [])
            tokens = [
                block["block_token"]
                for block in blocks
                if block.get("block_type") == "whiteboard"
            ]
            if len(tokens) == len(whiteboard_mermaids):
                for token, code in zip(tokens, whiteboard_mermaids):
                    result = lark_client.api_update_whiteboard(token, code)
                    if not result.get("ok"):
                        errors.append(
                            "whiteboard %s: %s" % (token, result.get("error"))
                        )
            else:
                errors.append(
                    "whiteboard count mismatch: created %s vs expected %s"
                    % (len(tokens), len(whiteboard_mermaids))
                )
        else:
            errors.append(output.get("error"))
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    return errors, overwritten


def write_runtime_snapshot(obj_token, content, backup_dir=None):
    if content is None:
        return None
    backup_dir = backup_dir or RUNTIME_BACKUP_DIR
    os.makedirs(backup_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(backup_dir, 0o700)
    except OSError:
        pass
    digest = hashlib.sha256(obj_token.encode("utf-8")).hexdigest()[:16]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = os.path.join(backup_dir, "%s_%s.xml" % (stamp, digest))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


@contextmanager
def document_lock(obj_token):
    obj_token = lark_client.validate_identifier(obj_token, "document identifier")
    lock_dir = os.path.join(tempfile.gettempdir(), "feishu-wiki-importer-locks")
    os.makedirs(lock_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(lock_dir, 0o700)
    except OSError:
        pass
    digest = hashlib.sha256(obj_token.encode("utf-8")).hexdigest()
    lock_file = open(
        os.path.join(lock_dir, digest + ".lock"), "a+", encoding="utf-8"
    )
    try:
        try:
            import fcntl
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        except ImportError:
            pass
        yield
    finally:
        try:
            import fcntl
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except ImportError:
            pass
        lock_file.close()


def overwrite_and_render(
    obj_token,
    processed_xml,
    whiteboard_mermaids,
    xml_temp_dir,
    original_xml=None,
    backup_dir=None,
    rollback_on_error=True,
    rollback_maps=None,
    rollback_title=None,
):
    if not obj_token or not isinstance(processed_xml, str) or not processed_xml.strip():
        return ["refused empty obj_token/content"]
    processed_xml = re.sub(r'\s+id="dox(cn)?[^"]+"', "", processed_xml)
    with document_lock(obj_token):
        if original_xml is None:
            fetched = lark_client.api_fetch(obj_token)
            if not fetched or not fetched.get("ok"):
                return ["refused overwrite: could not create a pre-write snapshot"]
            original_xml = fetched.get("data", {}).get("document", {}).get(
                "content", ""
            )
        if not whiteboards.can_restore_original_whiteboards(
            original_xml, maps=rollback_maps, chapter_title=rollback_title
        ):
            return [
                "refused overwrite: pre-write snapshot contains a whiteboard without Mermaid source; "
                "the original page cannot be restored safely"
            ]

        snapshot = write_runtime_snapshot(obj_token, original_xml, backup_dir)
        errors, overwritten = overwrite_once(
            obj_token, processed_xml, whiteboard_mermaids, xml_temp_dir
        )
        if not errors or not overwritten or not rollback_on_error or original_xml is None:
            if errors and snapshot:
                errors.append("local snapshot: %s" % snapshot)
            return errors

        if rollback_maps:
            rollback_xml, rollback_codes = (
                whiteboards.prepare_document_whiteboards_for_overwrite(
                    original_xml, maps=rollback_maps, chapter_title=rollback_title
                )
            )
        else:
            rollback_xml, rollback_codes = whiteboards.extract_existing_whiteboards(
                original_xml
            )
        rollback_xml = re.sub(r'\s+id="dox(cn)?[^"]+"', "", rollback_xml)
        rollback_errors, _ = overwrite_once(
            obj_token, rollback_xml, rollback_codes, xml_temp_dir
        )
        if rollback_errors:
            errors.append("rollback failed: %s" % rollback_errors)
        else:
            errors.append("write failed after overwrite; original document was restored")
        if snapshot:
            errors.append("local snapshot: %s" % snapshot)
        return errors
