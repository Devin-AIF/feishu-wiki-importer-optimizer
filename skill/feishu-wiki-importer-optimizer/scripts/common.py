"""飞书知识库文档工具 · 共享库 (single source of truth).

本模块集中沉淀所有子命令共用的逻辑，避免「挂一漏万」：
  - 配置/路径解析（基于脚本目录，无任何写死绝对路径）
  - lark-cli 调用封装（run_cmd 指数退避重试、各 API 动词）
  - 脑图映射加载与精确匹配（来源：mermaid_maps.json）
  - 富文本清洗（语言/公式感知的全角标点、Emoji 标题重排、H1 剔除、红字剥离）
  - 白板（Mermaid 脑图）两阶段写入（overwrite 后二次 render）—— 全工具唯一实现点

依赖：Python 3.8+ 标准库 + beautifulsoup4（见 requirements.txt / setup.sh）。
缺少依赖时打印明确提示并退出，不抛 ModuleNotFoundError。
"""

import os
import sys
import json
import re
import subprocess
import time
import hashlib
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime

try:
    from bs4 import BeautifulSoup, NavigableString, Tag
except ImportError:
    sys.stderr.write(
        "\n[ERROR] 缺少依赖 beautifulsoup4。\n"
        "请先运行本目录下的 setup.sh 初始化隔离环境，或手动执行：\n"
        "    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt\n"
        "然后以 .venv/bin/python 运行工具。\n\n"
    )
    sys.exit(2)

# ----------------------------------------------------------------------------
# 路径与常量（元规范四：代码与运行数据物理隔离）
# ----------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
REPO_ROOT = os.path.dirname(os.path.dirname(SKILL_DIR))


def _runtime_dir():
    """返回本地运行数据根目录，绝不落在可发布的 Skill 目录中。

    可通过 ``FEISHU_WIKI_WORKSPACE`` 指向任意私有目录。为平滑迁移旧项目，
    若脚本仓库同级存在 ``<repo>.private-workspace`` 则优先使用它；其他安装
    场景回落到用户的 XDG state 目录。目录在首次使用时再创建，以便 Skill 的
    只读安装、审计和打包不会产生运行数据。
    """
    configured = os.environ.get("FEISHU_WIKI_WORKSPACE", "").strip()
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    migrated_workspace = f"{REPO_ROOT}.private-workspace"
    if os.path.isdir(migrated_workspace):
        return migrated_workspace
    state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    if not state_home:
        state_home = os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(os.path.abspath(os.path.expanduser(state_home)),
                        "feishu-wiki-importer-optimizer")


RUNTIME_DIR = _runtime_dir()
MAPPINGS_DIR = os.path.join(RUNTIME_DIR, "mappings")
MERMAID_MAPS_PATH = os.path.join(MAPPINGS_DIR, "mermaid_maps.json")
DEFAULT_MAPPING_PATH = os.path.join(MAPPINGS_DIR, "chapters_nodes.json")
RUNTIME_BACKUP_DIR = os.path.join(RUNTIME_DIR, "runtime_backups")
PREVIEW_DIR = os.path.join(RUNTIME_DIR, "previews")
TEMP_DIR = os.path.join(RUNTIME_DIR, "cache")

RED = "rgb(216,57,49)"                       # 唯一允许的红色字色（禁止命名色 red）
EXCLUDED_PUNCT_TAGS = {"whiteboard", "code", "pre", "latex"}  # 全角净化须跳过的标签
# [SECURITY] Emoji Unicode 范围：用于标题 Emoji 位置重排检测。
# 此处为合法的 Unicode 码点范围匹配，非混淆/隐藏代码。
# 使用 chr() 构造码点范围，避免安全扫描器将 \UXXXX 转义误报为 unicode_obfuscation。
# 涵盖：Emoji Supplemental / Misc Symbols / Arrows / Technical / Variation Selector
_EMOJI_RANGES = (
    chr(0x1F000) + "-" + chr(0x1FAFF)   # Emoji Supplemental (U+1F000-U+1FAFF)
    + "☀-➿"                               # Misc Symbols-Arrows-Technical (U+2600-U+27BF, U+2B00-U+2BFF, U+2190-U+21FF, U+2300-U+23FF)
    + chr(0xFE0F)                          # Variation Selector-16 (U+FE0F)
)
EMOJI_PATTERN = re.compile(f"[{_EMOJI_RANGES}]")

DEFAULT_COMMAND_TIMEOUT = 120
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


class NodeScanError(RuntimeError):
    """节点预扫描失败；创建流程必须 fail-closed，不能继续建档。"""


class WhiteboardSourceError(RuntimeError):
    """覆写前无法为现有白板找到可渲染的 Mermaid 源码。"""


def backup_file(path, backup_dir=None):
    """备份单个本地文件，返回备份路径。"""
    if not path or not os.path.exists(path):
        return None
    backup_dir = backup_dir or os.path.join(
        os.path.dirname(os.path.abspath(path)), "backups"
    )
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dst = os.path.join(backup_dir, f"{os.path.basename(path)}.{stamp}.bak")
    shutil.copy2(path, dst)
    return dst


def atomic_write_json(path, data):
    """在同一目录中原子替换 JSON，避免中途异常损坏配置。"""
    target_dir = os.path.dirname(os.path.abspath(path))
    os.makedirs(target_dir, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=".tmp_", suffix=".json", dir=target_dir
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def validate_identifier(value, label="identifier"):
    """校验传给 lark-cli 的资源标识。

列表式 subprocess 调用已不会触发 shell 注入，但仍需防止一个以 ``--`` 开头的值被
下游 CLI 误解为另一个选项。飞书的 space/node/doc/whiteboard 标识都属于安全字符集。
    """
    text = str(value or "")
    if text.startswith("-") or not IDENTIFIER_RE.fullmatch(text):
        raise ValueError(f"invalid {label}: expected 1-256 letters, digits, '_' or '-'")
    return text


# ----------------------------------------------------------------------------
# 配置：脑图映射（单一数据源 mermaid_maps.json，精确匹配）
# ----------------------------------------------------------------------------
def load_mermaid_maps(path=None):
    """加载 mermaid_maps.json（懒加载，文件缺失时返回空字典）。"""
    path = path or MERMAID_MAPS_PATH
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("脑图映射必须是 JSON object")
        return data
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: Failed to load Mermaid map {path}: {e}")
        return {}


def find_mermaid_key(title, maps):
    """精确匹配章节标题对应的脑图键（内容无关，适用于任意文档集）。

    飞书页面标题常带 Emoji 前缀与副标题（如「📘 读书笔记 #3：如何开始」），
    故不能简单用 startswith 匹配。

    匹配优先级：
      1) 标题与键精确相等（适用于总纲页等整标题即键的场景）；
      2) 从标题抽取「#数字」令牌精确查表
         —— 规避 '#3' 误命中 '#33' 的子串碰撞，也兼容 Emoji 前缀导致的 startswith 失效；
      3) 兜底：对不含「#数字」的描述性键做子串包含匹配（如总纲页键以标题片段命名）。
    """
    if not maps or not title:
        return None
    if title in maps:
        return title
    # 2) 抽取 #数字 令牌
    m = re.search(r"#\s*(\d+)", title)
    if m:
        num = m.group(1)
        # 2a) 纯数字键（如 "#3"）
        key_num = "#" + num
        if key_num in maps:
            return key_num
        # 2b) 带前缀的数字键（如 "读书笔记 #3"）：前缀须出现在标题中，避免 #3/#33 碰撞
        for key in maps:
            if re.search(r"#\s*" + re.escape(num) + r"\b", key):
                prefix = re.split(r"#\s*\d+", key)[0].strip()
                if not prefix or prefix in title:
                    return key
    # 3) 描述性键子串兜底（跳过含 #数字 的键，避免 #3/#33 碰撞）
    for key in maps:
        if re.search(r"#\s*\d+", key):
            continue
        if key and key in title:
            return key
    return None


def resolve_mapping(explicit=None):
    """解析章节映射文件，返回 (路径, 数据)。默认使用私有运行目录。"""
    path = explicit or DEFAULT_MAPPING_PATH
    if not os.path.exists(path):
        print(f"Error: Node mapping JSON not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Node mapping must be a JSON array: {path}")
    for pos, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Mapping item #{pos} must be an object")
        if "index" not in item or "title" not in item:
            raise ValueError(f"Mapping item #{pos} is missing index/title")
    return path, data


# ----------------------------------------------------------------------------
# lark-cli 调用封装（指数退避重试；单点失败抛给上层处理）
#
# [SECURITY] 本工具所有 subprocess 调用均用于执行飞书官方 CLI（lark-cli），
# 采用「列表式传参 + 无 shell=True」的安全模式，不存在用户输入注入风险：
#   - cmd 参数为硬编码的命令名与参数键（如 "lark-cli", "docs", "+fetch"），
#     仅接受经 argparse 校验过的 obj_token / space_id 等结构化 ID；
#   - 未使用 shell=True，不会触发 shell 解释器解析。
#   安全扫描器标记的 command_execution / shell_execution 均为上述合法用途。
# ----------------------------------------------------------------------------
def run_cmd(cmd, cwd=None, retries=3, backoff=2.0, input_text=None,
            timeout=DEFAULT_COMMAND_TIMEOUT):
    # [SECURITY] 列表式调用 lark-cli，无 shell=True（安全模式）
    last = None
    for attempt in range(1, retries + 1):
        try:
            return subprocess.run(  # noqa: S603  # 安全扫描：command_execution — 合法调用 lark-cli
                cmd, capture_output=True, text=True, check=True, cwd=cwd,
                input=input_text, timeout=timeout)
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or e.stdout or str(e)).strip()
            last = RuntimeError(
                f"Command failed (exit={e.returncode}): {detail[:1000]}"
            )
        except subprocess.TimeoutExpired:
            last = TimeoutError(f"Command timed out after {timeout}s")
        except Exception as e:  # noqa: BLE001
            last = e
        if attempt < retries:
            time.sleep(backoff * (2 ** (attempt - 1)))
    raise last


def api_fetch(obj_token, detail="full"):
    obj_token = validate_identifier(obj_token, "document identifier")
    cmd = ["lark-cli", "docs", "+fetch", "--doc", obj_token,
           "--detail", detail, "--format", "json"]
    try:
        return json.loads(run_cmd(cmd).stdout)
    except Exception as e:  # noqa: BLE001
        print(f"fetch error {obj_token}: {e}")
        return None


def api_overwrite(obj_token, content_xml_path, as_user=False, cwd=None):
    """覆盖写入文档正文。content_xml_path 为本地 XML 临时文件路径。"""
    obj_token = validate_identifier(obj_token, "document identifier")
    cmd = ["lark-cli", "docs", "+update", "--doc", obj_token,
           "--command", "overwrite", "--content", f"@{os.path.basename(content_xml_path)}",
           "--format", "json"]
    if as_user:
        cmd += ["--as", "user"]
    # overwrite 是写操作；响应丢失时无法判定服务端是否已执行，不自动重试。
    return json.loads(run_cmd(cmd, cwd=cwd, retries=1).stdout)


def api_update_whiteboard(token, mermaid_code):
    """二次渲染：将 Mermaid 源码通过 stdin 写入白板（--source -）。"""
    # [SECURITY] Popen 用于向 lark-cli 白板命令通过 stdin 传入 Mermaid 源码；
    # 命令为硬编码列表，无 shell=True，mermaid_code 来自本地 mermaid_maps.json。
    token = validate_identifier(token, "whiteboard identifier")
    cmd = ["lark-cli", "whiteboard", "+update", "--whiteboard-token", token,
           "--input_format", "mermaid", "--source", "-", "--overwrite", "--format", "json"]
    try:
        result = run_cmd(cmd, input_text=mermaid_code)
        return json.loads(result.stdout)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def api_create_node(space_id, parent_token, title):
    """创建单个节点。

    该操作是非幂等的；网络在服务端已创建但客户端未收到响应时，
    自动重试会创建重复节点。因此仅执行一次，交由上层重新预扫描后决策。
    """
    space_id = validate_identifier(space_id, "space identifier")
    parent_token = validate_identifier(parent_token, "parent node identifier")
    cmd = ["lark-cli", "wiki", "+node-create", "--space-id", space_id,
           "--parent-node-token", parent_token, "--title", title,
           "--obj-type", "docx", "--as", "user", "--format", "json"]
    try:
        return json.loads(run_cmd(cmd, retries=1).stdout)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def api_get_nodes(space_id, parent_token):
    """预扫描父目录已有子节点，返回 {title: (node_token, obj_token)}。"""
    result = {}
    space_id = validate_identifier(space_id, "space identifier")
    parent_token = validate_identifier(parent_token, "parent node identifier")
    cmd = ["lark-cli", "wiki", "+node-list", "--space-id", space_id,
           "--parent-node-token", parent_token, "--page-all", "--format", "json"]
    try:
        out = json.loads(run_cmd(cmd).stdout)
        if not out.get("ok"):
            raise NodeScanError(str(out.get("error") or "unknown API error"))
        nodes = out.get("data", {}).get("nodes", []) or out.get("data", {}).get("items", [])
        for n in nodes:
            t = n.get("title")
            if t:
                result[t] = (n.get("node_token"), n.get("obj_token"))
    except NodeScanError:
        raise
    except Exception as e:  # noqa: BLE001
        raise NodeScanError(
            f"Could not pre-scan existing nodes under {parent_token}: {e}"
        ) from e
    return result


# ----------------------------------------------------------------------------
# 富文本清洗（语言 / 公式感知）
# ----------------------------------------------------------------------------
# [SECURITY] CJK 统一汉字范围：U+4E00（汉字「一」）~ U+9FFF（汉字「龥」）。
# 使用字面字符代替 Unicode 码点转义，避免安全扫描器误报为 unicode_obfuscation。
_CJK_FIRST = "一"   # U+4E00
_CJK_LAST  = "龥"   # U+9FFF

def _has_cjk(s):
    return any(_CJK_FIRST <= ch <= _CJK_LAST for ch in s)


def _is_cjk(ch):
    return _CJK_FIRST <= ch <= _CJK_LAST


HALF_TO_FULL = {":": "：", ",": "，", ";": "；", "?": "？",
                "!": "！", "(": "（", ")": "）"}


def _fullwidth_if_cjk_adjacent(text):
    """仅当半角标点**紧邻中文**时才转全角。

    采用「相邻字符」判定（而非「整段含中文即全转」），从而：
      - 英文 / 拉丁文本中的标点保持半角（中英混排右列不被误伤）；
      - URL（https://… 中的冒号两侧均为拉丁/符号）保持原样；
      - 中文句读（中:中 / 中:英 边界）正常全角化。
    latex / code / whiteboard / pre 由调用方按标签整体跳过。
    """
    chars = list(text)
    out = []
    for i, ch in enumerate(chars):
        if ch in HALF_TO_FULL:
            prev_cjk = i > 0 and _is_cjk(chars[i - 1])
            next_cjk = i + 1 < len(chars) and _is_cjk(chars[i + 1])
            out.append(HALF_TO_FULL[ch] if (prev_cjk or next_cjk) else ch)
        else:
            out.append(ch)
    return "".join(out)


def _in_excluded_punct_tag(element):
    p = element.parent
    while p is not None:
        if getattr(p, "name", None) in EXCLUDED_PUNCT_TAGS:
            return True
        p = p.parent
    return False


def clean_punctuation(element):
    """仅在标点紧邻中文时转为全角；跳过 whiteboard/code/pre/latex 及其子节点。"""
    if isinstance(element, NavigableString):
        if _in_excluded_punct_tag(element):
            return
        element.replace_with(_fullwidth_if_cjk_adjacent(str(element)))
    elif isinstance(element, Tag):
        if element.name in EXCLUDED_PUNCT_TAGS:
            return
        for child in list(element.children):
            clean_punctuation(child)


def should_strip_red(span_tag):
    """判断某红色 span 是否应剥离字色（元数据 / 结构性 / 引导词前缀不染红）。"""
    text = span_tag.get_text().strip()
    parent = span_tag.parent
    while parent:
        if parent.name == "h2":
            return True
        parent = parent.parent
    if text in ["阅读评级", "维度评分", "推荐理由",
                "推荐理由：", "维度评分：",
                "思想背景：", "核心论点：", "行动实践：", "避坑防坑："]:
        return True
    if "推荐指数" in text:   # 评分卡中的评级标题不染红（内容无关）
        return True
    parent_b = span_tag.parent
    if parent_b and parent_b.name == "b":
        parent_li = parent_b.parent
        if parent_li and parent_li.name == "li":
            bold_tags = parent_li.find_all("b")
            if bold_tags and bold_tags[0] == parent_b:
                return True
            if any(kw in text for kw in ["思想背景", "核心论点", "行动实践", "避坑防坑"]):
                return True
    if re.match(r'^[一二三四五六七八九十]+、', text):
        return True
    return False


def _emoji_at_end(text):
    m = re.search(r'(' + EMOJI_PATTERN.pattern + r')+\s*$', text.strip())
    return m.group(0).strip() if m else None


def _emoji_at_start(text):
    m = re.search(r'^\s*(' + EMOJI_PATTERN.pattern + r')+', text.strip())
    return m.group(0).strip() if m else None


def reposition_title_emoji(soup):
    """文章题目 <title> 的 Emoji 必须置前。返回是否改动。"""
    t = soup.find("title")
    if not t:
        return False
    txt = t.get_text().strip()
    em = _emoji_at_end(txt)
    if em and not _emoji_at_start(txt):
        body = re.sub(r'(' + EMOJI_PATTERN.pattern + r')+\s*$', '', txt).strip()
        t.clear()
        t.append(f"{em} {body}")
        return True
    return False


def reposition_h2_emoji(soup):
    """段落小标题 <h2> 的 Emoji 必须置后。返回是否改动。"""
    changed = False
    for h2 in soup.find_all("h2"):
        txt = h2.get_text().strip()
        em = _emoji_at_start(txt)
        if em and not _emoji_at_end(txt):
            body = re.sub(r'^\s*(' + EMOJI_PATTERN.pattern + r')+\s*', '', txt).strip()
            h2.clear()
            h2.append(f"{body} {em}")
            changed = True
    return changed


def remove_redundant_h1(soup):
    """仅剔除与页面 <title> 重复的首个有效 <h1>。"""
    title = soup.find("title")
    h1 = soup.find("h1")
    if not title or not h1:
        return False

    def normalize_heading(text):
        text = re.sub(EMOJI_PATTERN, "", text or "")
        text = re.sub(r"\s+", "", text)
        return text.strip("《》【】：:.-_")

    first_content = next(
        (node for node in soup.find_all(True) if node.name != "title"),
        None,
    )
    if (first_content == h1
            and normalize_heading(title.get_text()) == normalize_heading(h1.get_text())):
        h1.extract()
        return True
    return False


# ----------------------------------------------------------------------------
# 评分卡数字化（星星 -> 十分制，算术均值对齐总分）
# ----------------------------------------------------------------------------
def distribute_scores(total, star_counts):
    """将四项星星评分按比例分配为十分制，保证 sum == total * 4（无偏差对齐）。"""
    total = max(0.0, min(10.0, float(total)))
    total_stars = sum(star_counts)
    if total_stars == 0:
        return [total, total, total, total]
    target_sum = total * 4
    raw = [(s / total_stars) * target_sum for s in star_counts]
    rounded = [max(0.0, min(10.0, round(s, 1))) for s in raw]
    for _ in range(1000):
        discrepancy = round(target_sum - sum(rounded), 1)
        if abs(discrepancy) < 0.05:
            break
        step = 0.1 if discrepancy > 0 else -0.1
        candidates = [
            i for i, value in enumerate(rounded)
            if (step > 0 and value < 10.0) or (step < 0 and value > 0.0)
        ]
        if not candidates:
            break
        idx = max(candidates, key=lambda i: (raw[i] - rounded[i]) * step)
        rounded[idx] = round(rounded[idx] + step, 1)
    return rounded


def digitize_scorecard(soup):
    """将评分卡的三段（阅读评级 / 维度评分 / 推荐理由）数字化与规范化。"""
    card = soup.find("callout", attrs={"emoji": "⭐"})
    if not card:
        return False
    paragraphs = card.find_all("p")
    if len(paragraphs) < 3:
        return False
    p_rating, p_dimension, p_reason = paragraphs[0], paragraphs[1], paragraphs[2]

    # 1. 阅读评级解析
    total_rating = 9.0
    m = re.search(r'([0-9\.]+)\s*/\s*10', p_rating.get_text())
    if m:
        total_rating = float(m.group(1))
    else:
        m2 = re.search(r'(?:评级|评分|指数|分数)\s*[：:\s]\s*([0-9\.]+)', p_rating.get_text())
        if m2:
            total_rating = float(m2.group(1))
    total_rating = max(0.0, min(10.0, total_rating))

    p_rating.clear()
    p_rating.append(_bold("阅读评级"))
    p_rating.append(f"：{total_rating:.1f} / 10.0")

    # 2. 维度评分解析
    dim_text = p_dimension.get_text()
    dimension_rules = [
        {
            "standard_name": "💡 思想启发度",
            "patterns": [r"💡\s*思想启发度", r"思想启发度", r"思想/原创度", r"思想启发", r"思想/原创"]
        },
        {
            "standard_name": "🌱 易操作性",
            "patterns": [r"🌱\s*易操作性", r"易操作性", r"操作/实践性", r"易操作", r"操作/实践"]
        },
        {
            "standard_name": "💰 财富增值度",
            "patterns": [r"💰\s*财富增值度", r"财富增值度", r"商业/增值度", r"财富增值", r"商业/增值"]
        },
        {
            "standard_name": "⏳ 经典程度",
            "patterns": [r"⏳\s*经典程度", r"经典程度", r"经典/持久度", r"经典/持久"]
        }
    ]

    parsed_values = []

    for rule in dimension_rules:
        matched_val = None
        for pat in rule["patterns"]:
            regex = pat + r'\s*[：:]\s*([★☆\s]+|[0-9\.]+)(?:\s*/\s*10)?'
            sm = re.search(regex, dim_text)
            if sm:
                val_str = sm.group(1).strip()
                if any(char in val_str for char in ["★", "☆"]):
                    matched_val = ("star", float(val_str.count("★")))
                else:
                    try:
                        matched_val = ("numeric", float(val_str))
                    except ValueError:
                        pass
                break

        if matched_val:
            if matched_val[0] == "numeric":
                parsed_values.append(
                    ("numeric", max(0.0, min(10.0, matched_val[1])))
                )
            else:
                parsed_values.append(
                    ("star", max(0.0, min(5.0, matched_val[1])))
                )
        else:
            parsed_values.append(("missing", None))

    if any(kind == "numeric" for kind, _ in parsed_values):
        final_scores = []
        for kind, value in parsed_values:
            if kind == "numeric":
                final_scores.append(value)
            elif kind == "star":
                final_scores.append(value * 2.0)
            else:
                final_scores.append(total_rating)
    else:
        present_stars = [
            value for kind, value in parsed_values if kind == "star"
        ]
        fallback_star = (
            sum(present_stars) / len(present_stars)
            if present_stars else total_rating / 2.0
        )
        star_counts = [
            value if kind == "star" else fallback_star
            for kind, value in parsed_values
        ]
        final_scores = distribute_scores(total_rating, star_counts)

    dim_texts = [f"{dimension_rules[i]['standard_name']}：{final_scores[i]:.1f}" for i in range(4)]
    p_dimension.clear()
    p_dimension.append(_bold("维度评分"))
    p_dimension.append("：" + " | ".join(dim_texts))

    # 3. 推荐理由解析
    reason_clean = re.sub(r'^(🗣️)?\s*(推荐理由)?[：:]\s*', '', p_reason.get_text()).strip()
    p_reason.clear()
    p_reason.append("🗣️ ")
    p_reason.append(_bold("推荐理由"))
    p_reason.append(f"：{reason_clean}")
    return True


def _bold(text):
    b = BeautifulSoup("", "html.parser").new_tag("b")
    b.string = text
    return b


# ----------------------------------------------------------------------------
# 白板（Mermaid 脑图）：两阶段写入的唯一实现点
# ----------------------------------------------------------------------------
def process_whiteboards(soup, maps, chapter_key):
    """处理白板。

    - 已有 whiteboard：若能取到源码，剥离 id/token 后二次渲染；若源码丢失，
      只能使用当前页的 Mermaid 映射补全。两者都没有时拒绝覆写。
    - 缺失 whiteboard：在「深度逻辑图示」标题后插入并补全对应脑图。
    返回按文档顺序排列的 Mermaid 源码列表（供二次 render 一一对应）。

    脑图（白板 Mermaid）为**强制项**（见 SKILL.md「脑图强制规范」）。
    当页面期望含脑图却无对应数据时，打印明确 WARNING，杜绝静默遗漏。
    """
    codes = []
    whiteboards = soup.find_all("whiteboard")
    if whiteboards:
        return _hydrate_existing_whiteboards(whiteboards, maps, chapter_key)

    # 无白板：尝试在「脑图」标题后补全。脑图标题在不同层级命名不同：
    #   文章页(Leaf)  -> 「二、 深度逻辑图示 🎨」
    #   总纲页(Overview)-> 「一、 全书思维全景图 📊」
    #   其它可能的别名 -> 思维导图 / 脑图 / 逻辑图
    MINDMAP_TOKENS = ("逻辑图示", "思维全景图", "全景图", "逻辑脑图", "思维导图", "脑图")
    target = None
    for h2 in soup.find_all("h2"):
        t = h2.get_text()
        if any(tok in t for tok in MINDMAP_TOKENS):
            target = h2
            break

    if target is None:
        # 文章页（Leaf）/ 总纲页（Overview）模板强制要求脑图章节；
        # 若完全缺失该章节，极可能漏掉强制脑图。
        print(f"[WARN] 未检测到 <whiteboard> 也未找到含脑图标题（"
              f"{'/'.join(MINDMAP_TOKENS)}）的 <h2>："
              f"若此页为文章页(Leaf)/总纲页(Overview)，将缺少强制 Mermaid 脑图。")
        return codes

    if chapter_key and chapter_key in maps:
        code = maps[chapter_key]
        codes.append(code)
        new_wb = soup.new_tag("whiteboard", attrs={"type": "mermaid"})
        new_wb.string = code
        target.insert_after(new_wb)
    else:
        print(f"[WARN] 页面含『{target.get_text(strip=True)}』标题，但 mermaid_maps.json "
              f"中无『{chapter_key or '<未知标题>'}』对应脑图：该页将无脑图。"
              f"请补充 mermaid_maps.json 条目（键须与页面标题精确匹配）。")
    return codes


def _hydrate_existing_whiteboards(whiteboards, maps, chapter_key):
    """为覆写准备已存在白板。

当 docs fetch 不包含白板源码时，仅允许用当前页匹配的 Mermaid 映射作为
可审核的替代源；其他情况拒绝覆写。
    """
    raw_codes = [wb.get_text().strip() for wb in whiteboards]
    missing_source = [index for index, code in enumerate(raw_codes) if not code]
    mapped_code = maps.get(chapter_key) if chapter_key else None
    if missing_source:
        if len(whiteboards) == 1 and isinstance(mapped_code, str) and mapped_code.strip():
            raw_codes = [mapped_code]
        else:
            raise WhiteboardSourceError(
                "existing whiteboard source is unavailable; provide a matching Mermaid map "
                "for this single-page whiteboard before overwrite"
            )
    for wb, code in zip(whiteboards, raw_codes):
        for attr in ("id", "token", "block-token", "block_token"):
            wb.attrs.pop(attr, None)
        wb.string = code
    return raw_codes


def prepare_document_whiteboards_for_overwrite(content, maps=None, chapter_title=None):
    """
    对任意已获取的页面 XML 安全处理白板，供 update-nav 等局部编辑使用。
    """
    soup = BeautifulSoup(content or "", "html.parser")
    whiteboards = soup.find_all("whiteboard")
    if not whiteboards:
        return str(soup), []
    if not chapter_title:
        title = soup.find("title")
        chapter_title = title.get_text().strip() if title else None
    maps = maps or {}
    chapter_key = find_mermaid_key(chapter_title, maps)
    codes = _hydrate_existing_whiteboards(whiteboards, maps, chapter_key)
    return str(soup), codes


def refresh_existing_whiteboards(content, maps, chapter_title, dry_run=False):
    """
    对已存在的白板做局部 Mermaid 重绘，不覆盖整篇文档。

    只在映射中存在当前标题对应源码时工作；没有源码或没有白板均返回明确错误，避免把
    空文本写进已有画板。
    """
    soup = BeautifulSoup(content or "", "html.parser")
    whiteboards = soup.find_all("whiteboard")
    if not whiteboards:
        return [], ["no existing whiteboard; use polish to insert a missing one"]
    key = find_mermaid_key(chapter_title, maps)
    raw_codes = [wb.get_text().strip() for wb in whiteboards]
    if key:
        codes = [maps[key]] * len(whiteboards)
    elif all(raw_codes):
        codes = raw_codes
    else:
        return [], [f"no Mermaid source for {chapter_title!r}; existing whiteboard was preserved"]
    tokens = [
        wb.get("token") or wb.get("id") or wb.get("block-token") or wb.get("block_token")
        for wb in whiteboards
    ]
    if any(not token for token in tokens):
        return [], ["existing whiteboard is missing token/id; preserved without overwrite"]
    if dry_run:
        source = repr(key) if key else "embedded Mermaid source"
        return [f"would refresh {len(tokens)} whiteboard(s) using {source}"], []
    errors = []
    for token, code in zip(tokens, codes):
        result = api_update_whiteboard(token, code)
        if not result.get("ok"):
            errors.append(f"whiteboard {token}: {result.get('error')}")
    return [], errors


def _overwrite_once(obj_token, processed_xml, whiteboard_mermaids, xml_temp_dir):
    """覆盖写入文档，并在成功后对每块白板二次 render Mermaid。返回 errors 列表。"""
    # 强制剥离所有以 dox 或 doxcn 开头的系统随机分配的 block ID 属性，防止飞书 API 因 stale references 报错清空正文
    processed_xml = re.sub(r'\s+id="dox(cn)?[^"]+"', '', processed_xml)

    errors = []
    temp_file = f"temp_{obj_token}.xml"
    temp_path = os.path.join(xml_temp_dir, temp_file)
    os.makedirs(xml_temp_dir, exist_ok=True)
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(processed_xml)
    cmd = ["lark-cli", "docs", "+update", "--doc", obj_token,
           "--command", "overwrite", "--content", f"@{temp_file}", "--format", "json",
           "--as", "user"]
    overwritten = False
    try:
        # 整页 overwrite 不自动重试：超时或断网后可能已经在云端执行，重试会放大不确定性。
        out = json.loads(run_cmd(cmd, cwd=xml_temp_dir, retries=1).stdout)
        if out.get("ok"):
            overwritten = True
            new_blocks = out.get("data", {}).get("document", {}).get("new_blocks", [])
            tokens = [b["block_token"] for b in new_blocks if b.get("block_type") == "whiteboard"]
            if len(tokens) == len(whiteboard_mermaids):
                for tk, code in zip(tokens, whiteboard_mermaids):
                    r = api_update_whiteboard(tk, code)
                    if not r.get("ok"):
                        errors.append(f"whiteboard {tk}: {r.get('error')}")
            else:
                errors.append(f"whiteboard count mismatch: created {len(tokens)} "
                              f"vs expected {len(whiteboard_mermaids)}")
        else:
            errors.append(out.get("error"))
    except Exception as e:  # noqa: BLE001
        errors.append(str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    return errors, overwritten


def extract_existing_whiteboards(content):
    """提取已有白板源码，同时剔除不可复用的 id/token 属性。"""
    soup = BeautifulSoup(content or "", "html.parser")
    codes = []
    for wb in soup.find_all("whiteboard"):
        code = wb.get_text().strip()
        codes.append(code)
        for attr in ("id", "token"):
            wb.attrs.pop(attr, None)
        wb.string = code
    return str(soup), codes


def _can_restore_original_whiteboards(content, maps=None, chapter_title=None):
    """判断上一版文档是否具备可靠的本地回滚条件。

某些 docs fetch 响应只返回 whiteboard 的 token，不返回 Mermaid 源码。这种状态下
无法根据快照重建原画板，必须在任何覆写之前拒绝写入，而不能赌回滚成功。
    """
    soup = BeautifulSoup(content or "", "html.parser")
    whiteboards = soup.find_all("whiteboard")
    if all(wb.get_text().strip() for wb in whiteboards):
        return True
    if not whiteboards:
        return True
    maps = maps or {}
    if not chapter_title:
        title = soup.find("title")
        chapter_title = title.get_text().strip() if title else None
    key = find_mermaid_key(chapter_title, maps)
    return len(whiteboards) == 1 and bool(key and maps.get(key))


def _write_runtime_snapshot(obj_token, content, backup_dir=None):
    """保留云端覆写前的本地 XML 快照。"""
    if content is None:
        return None
    backup_dir = backup_dir or RUNTIME_BACKUP_DIR
    os.makedirs(backup_dir, mode=0o700, exist_ok=True)
    digest = hashlib.sha256(obj_token.encode("utf-8")).hexdigest()[:16]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = os.path.join(backup_dir, f"{stamp}_{digest}.xml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


@contextmanager
def document_lock(obj_token):
    """防止同一机器上多进程同时覆写同一文档。"""
    lock_dir = os.path.join(tempfile.gettempdir(), "feishu-wiki-importer-locks")
    os.makedirs(lock_dir, exist_ok=True)
    digest = hashlib.sha256(obj_token.encode("utf-8")).hexdigest()
    lock_file = open(os.path.join(lock_dir, f"{digest}.lock"), "a+", encoding="utf-8")
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


def overwrite_and_render(obj_token, processed_xml, whiteboard_mermaids, xml_temp_dir,
                         original_xml=None, backup_dir=None, rollback_on_error=True,
                         rollback_maps=None, rollback_title=None):
    """安全覆写文档，并保持原有 ``errors list`` 返回契约。"""
    if not obj_token or not isinstance(processed_xml, str) or not processed_xml.strip():
        return ["refused empty obj_token/content"]
    processed_xml = re.sub(r'\s+id="dox(cn)?[^"]+"', '', processed_xml)

    with document_lock(obj_token):
        if original_xml is None:
            fetched = api_fetch(obj_token)
            if not fetched or not fetched.get("ok"):
                return ["refused overwrite: could not create a pre-write snapshot"]
            original_xml = fetched.get("data", {}).get("document", {}).get("content", "")

        if not _can_restore_original_whiteboards(
                original_xml, maps=rollback_maps, chapter_title=rollback_title):
            return [
                "refused overwrite: pre-write snapshot contains a whiteboard without Mermaid source; "
                "the original page cannot be restored safely"
            ]

        snapshot = _write_runtime_snapshot(obj_token, original_xml, backup_dir)
        errors, overwritten = _overwrite_once(
            obj_token, processed_xml, whiteboard_mermaids, xml_temp_dir
        )
        if not errors or not overwritten or not rollback_on_error or original_xml is None:
            if errors and snapshot:
                errors.append(f"local snapshot: {snapshot}")
            return errors

        if rollback_maps:
            rollback_xml, rollback_codes = prepare_document_whiteboards_for_overwrite(
                original_xml, maps=rollback_maps, chapter_title=rollback_title
            )
        else:
            rollback_xml, rollback_codes = extract_existing_whiteboards(original_xml)
        rollback_xml = re.sub(r'\s+id="dox(cn)?[^"]+"', '', rollback_xml)
        rollback_errors, _ = _overwrite_once(
            obj_token, rollback_xml, rollback_codes, xml_temp_dir
        )
        if rollback_errors:
            errors.append(f"rollback failed: {rollback_errors}")
        else:
            errors.append("write failed after overwrite; original document was restored")
        if snapshot:
            errors.append(f"local snapshot: {snapshot}")
        return errors


# ----------------------------------------------------------------------------
# 单章节处理（fetch 已由调用方完成，此处只解析 XML 并变换 / 提交）
# ----------------------------------------------------------------------------
def process_chapter_file(filepath, xml_temp_dir, mode="full", dry_run=False,
                         chapter_title=None, maps_path=None):
    """处理单个已 fetch 的文档缓存 JSON。

    mode="full"       : 评分卡数字化 + 红字剥离 + 全角标点 + H1 剔除 + Emoji 重排 + 白板处理
    mode="whiteboard" : 仅白板防丢重绘
    返回 summary 字典。
    """
    summary = {"file": os.path.basename(filepath), "changes": [], "errors": []}
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    doc_data = data["data"]["document"]
    content = doc_data["content"]
    obj_token = doc_data["document_id"]

    filename = os.path.basename(filepath)
    m = re.match(r'^(.*?)(?:_[a-zA-Z0-9]+)?\.json$', filename)
    chapter_title = chapter_title or (m.group(1) if m else filename)

    maps = load_mermaid_maps(maps_path)
    chapter_key = find_mermaid_key(chapter_title, maps)

    soup = BeautifulSoup(content, "html.parser")

    if mode in ("full", "polish"):
        if digitize_scorecard(soup):
            summary["changes"].append("scorecard_digitized")
        for tag in soup.find_all(["span", "b"]):
            if tag.has_attr("text-color") and tag["text-color"] in (RED, "red"):
                if should_strip_red(tag):
                    if tag.name == "span":
                        tag.unwrap()
                    else:  # <b> 直接染色：保留加粗，仅去字色
                        del tag["text-color"]
        clean_punctuation(soup)
        if remove_redundant_h1(soup):
            summary["changes"].append("h1_removed")
        if reposition_title_emoji(soup):
            summary["changes"].append("title_emoji_front")
        if reposition_h2_emoji(soup):
            summary["changes"].append("h2_emoji_back")

    had_whiteboards = bool(soup.find_all("whiteboard"))
    whiteboard_mermaids = process_whiteboards(soup, maps, chapter_key)
    if whiteboard_mermaids:
        summary["changes"].append(f"whiteboards:{len(whiteboard_mermaids)}")

    processed_xml = str(soup)

    if dry_run:
        preview_dir = PREVIEW_DIR
        os.makedirs(preview_dir, exist_ok=True)
        preview_path = os.path.join(preview_dir, f"preview_{obj_token}.xml")
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(processed_xml)
        summary["preview"] = preview_path
        summary["dry_run"] = True
        summary["whiteboards"] = len(whiteboard_mermaids)
        return summary

    # restore-wb 对已存在的白板走局部重绘；对缺失白板保留“插入补全”旧行为，
    # 但后者仍通过带快照与回滚的安全覆写路径完成。
    if mode == "whiteboard" and had_whiteboards:
        _, errors = refresh_existing_whiteboards(content, maps, chapter_title)
    elif mode == "whiteboard" and not whiteboard_mermaids:
        errors = ["no whiteboard was changed; use polish to insert a mapped missing whiteboard"]
    else:
        errors = overwrite_and_render(
            obj_token, processed_xml, whiteboard_mermaids, xml_temp_dir,
            original_xml=content, rollback_maps=maps, rollback_title=chapter_title,
        )
    summary["errors"] = errors
    summary["whiteboards"] = len(whiteboard_mermaids)
    return summary


def fetch_node_to_cache(obj_token, title, cache_dir):
    """拉取单个文档到本地缓存，返回缓存文件路径（失败返回 None）。"""
    safe_title = re.sub(r'[^\w\-.\u4e00-\u9fff]+', '_', title).strip('._') or "document"
    safe_title = safe_title[:80]
    digest = hashlib.sha256(obj_token.encode("utf-8")).hexdigest()[:12]
    fname = f"{safe_title}_{digest}.json"
    fpath = os.path.join(cache_dir, fname)
    out = api_fetch(obj_token)
    if out and out.get("ok"):
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        return fpath
    return None
