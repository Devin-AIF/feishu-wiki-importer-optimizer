"""可发布 Skill 代码与私有运行数据的路径边界。"""

import os


PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.dirname(PACKAGE_DIR)
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
REPO_ROOT = os.path.dirname(os.path.dirname(SKILL_DIR))


def runtime_dir():
    """返回私有运行数据根目录，绝不落在可发布 Skill 目录中。"""
    configured = os.environ.get("FEISHU_WIKI_WORKSPACE", "").strip()
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    migrated_workspace = "%s.private-workspace" % REPO_ROOT
    if os.path.isdir(migrated_workspace):
        return migrated_workspace
    state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    if not state_home:
        state_home = os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(
        os.path.abspath(os.path.expanduser(state_home)),
        "feishu-wiki-importer-optimizer",
    )


RUNTIME_DIR = runtime_dir()
MAPPINGS_DIR = os.path.join(RUNTIME_DIR, "mappings")
MERMAID_MAPS_PATH = os.path.join(MAPPINGS_DIR, "mermaid_maps.json")
DEFAULT_MAPPING_PATH = os.path.join(MAPPINGS_DIR, "chapters_nodes.json")
RUNTIME_BACKUP_DIR = os.path.join(RUNTIME_DIR, "runtime_backups")
PREVIEW_DIR = os.path.join(RUNTIME_DIR, "previews")
TEMP_DIR = os.path.join(RUNTIME_DIR, "cache")
