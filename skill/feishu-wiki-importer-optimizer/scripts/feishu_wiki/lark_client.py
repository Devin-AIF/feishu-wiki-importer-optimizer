"""通过列表式参数安全调用飞书 `lark-cli`。"""

import json
import os
import re
import subprocess
import time


DEFAULT_COMMAND_TIMEOUT = 120
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


class NodeScanError(RuntimeError):
    """节点预扫描失败；创建流程必须 fail-closed。"""


def validate_identifier(value, label="identifier"):
    text = str(value or "")
    if text.startswith("-") or not IDENTIFIER_RE.fullmatch(text):
        raise ValueError(
            "invalid %s: expected 1-256 letters, digits, '_' or '-'" % label
        )
    return text


def run_cmd(
    cmd,
    cwd=None,
    retries=3,
    backoff=2.0,
    input_text=None,
    timeout=DEFAULT_COMMAND_TIMEOUT,
):
    """执行已拆分的 CLI 参数；不使用 shell。"""
    if not isinstance(retries, int) or retries < 1:
        raise ValueError("retries must be a positive integer")
    last = None
    for attempt in range(1, retries + 1):
        try:
            return subprocess.run(  # noqa: S603
                cmd,
                capture_output=True,
                text=True,
                check=True,
                cwd=cwd,
                input=input_text,
                timeout=timeout,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc)).strip()
            last = RuntimeError(
                "Command failed (exit=%s): %s" % (exc.returncode, detail[:1000])
            )
        except subprocess.TimeoutExpired:
            last = TimeoutError("Command timed out after %ss" % timeout)
        except Exception as exc:  # noqa: BLE001
            last = exc
        if attempt < retries:
            time.sleep(backoff * (2 ** (attempt - 1)))
    raise last


def api_fetch(obj_token, detail="full"):
    obj_token = validate_identifier(obj_token, "document identifier")
    cmd = [
        "lark-cli", "docs", "+fetch", "--doc", obj_token,
        "--detail", detail, "--format", "json",
    ]
    try:
        return json.loads(run_cmd(cmd).stdout)
    except Exception as exc:  # noqa: BLE001
        print("fetch error %s: %s" % (obj_token, exc))
        return None


def api_overwrite(obj_token, content_xml_path, as_user=False, cwd=None):
    obj_token = validate_identifier(obj_token, "document identifier")
    cmd = [
        "lark-cli", "docs", "+update", "--doc", obj_token,
        "--command", "overwrite", "--content", "@" + os.path.basename(content_xml_path),
        "--format", "json",
    ]
    if as_user:
        cmd += ["--as", "user"]
    return json.loads(run_cmd(cmd, cwd=cwd, retries=1).stdout)


def api_update_whiteboard(token, mermaid_code):
    token = validate_identifier(token, "whiteboard identifier")
    cmd = [
        "lark-cli", "whiteboard", "+update", "--whiteboard-token", token,
        "--input_format", "mermaid", "--source", "-", "--overwrite",
        "--format", "json",
    ]
    try:
        return json.loads(run_cmd(cmd, input_text=mermaid_code).stdout)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def api_create_node(space_id, parent_token, title):
    space_id = validate_identifier(space_id, "space identifier")
    parent_token = validate_identifier(parent_token, "parent node identifier")
    cmd = [
        "lark-cli", "wiki", "+node-create", "--space-id", space_id,
        "--parent-node-token", parent_token, "--title", title,
        "--obj-type", "docx", "--as", "user", "--format", "json",
    ]
    try:
        return json.loads(run_cmd(cmd, retries=1).stdout)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def api_get_nodes(space_id, parent_token):
    result = {}
    space_id = validate_identifier(space_id, "space identifier")
    parent_token = validate_identifier(parent_token, "parent node identifier")
    cmd = [
        "lark-cli", "wiki", "+node-list", "--space-id", space_id,
        "--parent-node-token", parent_token, "--page-all", "--format", "json",
    ]
    try:
        output = json.loads(run_cmd(cmd).stdout)
        if not output.get("ok"):
            raise NodeScanError(str(output.get("error") or "unknown API error"))
        nodes = output.get("data", {}).get("nodes", []) or output.get(
            "data", {}
        ).get("items", [])
        for node in nodes:
            title = node.get("title")
            if title:
                result[title] = (node.get("node_token"), node.get("obj_token"))
    except NodeScanError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise NodeScanError(
            "Could not pre-scan existing nodes under %s: %s" % (parent_token, exc)
        ) from exc
    return result
