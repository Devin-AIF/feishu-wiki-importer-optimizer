"""历史兼容导出层。

正式实现已按职责拆分到 `feishu_wiki/` 包。旧 CLI 和用户脚本可继续
`from common import ...`；新代码应直接从对应子模块导入。
"""

from feishu_wiki import lark_client as _lark_client
from feishu_wiki import service as _service
from feishu_wiki import storage as _storage
from feishu_wiki import transforms as _transforms
from feishu_wiki import whiteboards as _whiteboards
from feishu_wiki import writer as _writer
from feishu_wiki.paths import (
    DEFAULT_MAPPING_PATH,
    MAPPINGS_DIR,
    MERMAID_MAPS_PATH,
    PREVIEW_DIR,
    REPO_ROOT,
    RUNTIME_BACKUP_DIR,
    RUNTIME_DIR,
    SCRIPT_DIR,
    SKILL_DIR,
    TEMP_DIR,
    runtime_dir as _runtime_dir,
)


RED = _transforms.RED
EXCLUDED_PUNCT_TAGS = _transforms.EXCLUDED_PUNCT_TAGS
EMOJI_PATTERN = _transforms.EMOJI_PATTERN
HALF_TO_FULL = _transforms.HALF_TO_FULL
DEFAULT_COMMAND_TIMEOUT = _lark_client.DEFAULT_COMMAND_TIMEOUT
IDENTIFIER_RE = _lark_client.IDENTIFIER_RE
NodeScanError = _lark_client.NodeScanError
WhiteboardSourceError = _whiteboards.WhiteboardSourceError

backup_file = _storage.backup_file
atomic_write_json = _storage.atomic_write_json
load_mermaid_maps = _storage.load_mermaid_maps
find_mermaid_key = _storage.find_mermaid_key
resolve_mapping = _storage.resolve_mapping

validate_identifier = _lark_client.validate_identifier
run_cmd = _lark_client.run_cmd
api_fetch = _lark_client.api_fetch
api_overwrite = _lark_client.api_overwrite
api_update_whiteboard = _lark_client.api_update_whiteboard
api_create_node = _lark_client.api_create_node
api_get_nodes = _lark_client.api_get_nodes

_has_cjk = _transforms._has_cjk
_is_cjk = _transforms._is_cjk
_fullwidth_if_cjk_adjacent = _transforms._fullwidth_if_cjk_adjacent
_in_excluded_punct_tag = _transforms._in_excluded_punct_tag
clean_punctuation = _transforms.clean_punctuation
should_strip_red = _transforms.should_strip_red
_emoji_at_end = _transforms._emoji_at_end
_emoji_at_start = _transforms._emoji_at_start
reposition_title_emoji = _transforms.reposition_title_emoji
reposition_h2_emoji = _transforms.reposition_h2_emoji
remove_redundant_h1 = _transforms.remove_redundant_h1
distribute_scores = _transforms.distribute_scores
digitize_scorecard = _transforms.digitize_scorecard
_bold = _transforms._bold

process_whiteboards = _whiteboards.process_whiteboards
_hydrate_existing_whiteboards = _whiteboards._hydrate_existing_whiteboards
prepare_document_whiteboards_for_overwrite = (
    _whiteboards.prepare_document_whiteboards_for_overwrite
)
refresh_existing_whiteboards = _whiteboards.refresh_existing_whiteboards
extract_existing_whiteboards = _whiteboards.extract_existing_whiteboards
_can_restore_original_whiteboards = _whiteboards.can_restore_original_whiteboards
_overwrite_once = _writer.overwrite_once
_write_runtime_snapshot = _writer.write_runtime_snapshot
document_lock = _writer.document_lock
overwrite_and_render = _writer.overwrite_and_render
process_chapter_file = _service.process_chapter_file
fetch_node_to_cache = _service.fetch_node_to_cache
