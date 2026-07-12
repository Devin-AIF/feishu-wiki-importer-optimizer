"""可发布 Skill 代码与私有项目工作区的路径边界。"""

import json
import os
import re


PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.dirname(PACKAGE_DIR)
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
REPO_ROOT = os.path.dirname(os.path.dirname(SKILL_DIR))
PROJECT_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


class WorkspacePathError(ValueError):
    """工作区或项目配置不安全/不可读。"""


def _default_workspace():
    migrated_workspace = "%s.private-workspace" % REPO_ROOT
    if os.path.isdir(migrated_workspace):
        return os.path.abspath(migrated_workspace)
    state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    if not state_home:
        state_home = os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(
        os.path.abspath(os.path.expanduser(state_home)),
        "feishu-wiki-importer-optimizer",
    )


def runtime_dir(explicit=None):
    """按 CLI > 环境变量 > 安全默认值解析私有工作区。"""
    configured = explicit or os.environ.get("FEISHU_WIKI_WORKSPACE", "").strip()
    workspace = (
        os.path.abspath(os.path.expanduser(configured))
        if configured
        else _default_workspace()
    )
    home = os.path.abspath(os.path.expanduser("~"))
    if workspace in (os.path.abspath(os.sep), home):
        raise WorkspacePathError("拒绝将根目录或用户 HOME 作为工作区")
    if workspace == SKILL_DIR or workspace.startswith(SKILL_DIR + os.sep):
        raise WorkspacePathError("工作区不得位于可发布 Skill 目录内")
    if os.path.isdir(os.path.join(REPO_ROOT, ".git")) and (
        workspace == REPO_ROOT or workspace.startswith(REPO_ROOT + os.sep)
    ):
        raise WorkspacePathError("工作区不得位于开发仓库内")
    return workspace


def _load_workspace_project(workspace):
    config_path = os.path.join(workspace, "workspace.json")
    if not os.path.exists(config_path):
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise WorkspacePathError("workspace.json 不可读: %s" % exc)
    if not isinstance(data, dict):
        raise WorkspacePathError("workspace.json 必须是 JSON object")
    project = data.get("default_project")
    if not isinstance(project, str) or not PROJECT_SLUG_RE.fullmatch(project):
        raise WorkspacePathError("workspace.json 的 default_project 不合法")
    return project


def project_name(workspace, explicit=None):
    """按 CLI > workspace.json > default 选择项目。"""
    selected = explicit or _load_workspace_project(workspace) or "default"
    if not isinstance(selected, str) or not PROJECT_SLUG_RE.fullmatch(selected):
        raise WorkspacePathError(
            "项目名必须是 1-64 位小写字母、数字或连字符"
        )
    return selected


def _configure_values(workspace=None, project=None):
    workspace = runtime_dir(workspace)
    selected = project_name(workspace, project)
    project_dir = os.path.join(workspace, "projects", selected)
    project_layout = os.path.isdir(project_dir) or os.path.isfile(
        os.path.join(workspace, "workspace.json")
    )
    legacy_mappings = os.path.join(workspace, "mappings")
    outline = os.path.join(project_dir, "config", "outline.json")
    project_maps = os.path.join(project_dir, "generated", "mermaid_maps.json")
    return {
        "RUNTIME_DIR": workspace,
        "WORKSPACE_CONFIG_PATH": os.path.join(workspace, "workspace.json"),
        "PROJECT": selected,
        "PROJECT_DIR": project_dir,
        "PROJECT_CONFIG_PATH": os.path.join(project_dir, "project.json"),
        "SOURCE_DIR": os.path.join(project_dir, "source"),
        "SOURCE_CHAPTERS_DIR": os.path.join(project_dir, "source", "chapters"),
        "SOURCE_IMAGES_DIR": os.path.join(project_dir, "source", "images"),
        "OUTLINE_PATH": outline,
        "REMOTE_NODES_PATH": os.path.join(project_dir, "state", "remote_nodes.json"),
        "UPLOADED_IMAGES_PATH": os.path.join(project_dir, "state", "uploaded_images.json"),
        "PREPARED_DIR": os.path.join(project_dir, "generated", "prepared"),
        "MAPPINGS_DIR": legacy_mappings,
        "LEGACY_MAPPING_PATH": os.path.join(legacy_mappings, "chapters_nodes.json"),
        "LEGACY_MERMAID_MAPS_PATH": os.path.join(legacy_mappings, "mermaid_maps.json"),
        "DEFAULT_MAPPING_PATH": (
            outline if project_layout else os.path.join(legacy_mappings, "chapters_nodes.json")
        ),
        "MERMAID_MAPS_PATH": (
            project_maps if project_layout else os.path.join(legacy_mappings, "mermaid_maps.json")
        ),
        "RUNTIME_BACKUP_DIR": (
            os.path.join(project_dir, "backups", "runtime")
            if project_layout
            else os.path.join(workspace, "runtime_backups")
        ),
        "PREVIEW_DIR": (
            os.path.join(project_dir, "previews")
            if project_layout
            else os.path.join(workspace, "previews")
        ),
        "TEMP_DIR": (
            os.path.join(project_dir, "cache")
            if project_layout
            else os.path.join(workspace, "cache")
        ),
        "PROJECT_LAYOUT": project_layout,
    }


def configure(workspace=None, project=None):
    """更新当前进程的工作区路径，返回路径字典。"""
    values = _configure_values(workspace, project)
    globals().update(values)
    return dict(values)


try:
    configure()
except WorkspacePathError:
    # 允许主 CLI 完成参数解析，使显式 --workspace 能覆盖错误环境变量。
    # 各 CLI 的 main() 会再次 configure，未覆盖的不安全配置仍会报错。
    globals().update(_configure_values(_default_workspace(), None))
