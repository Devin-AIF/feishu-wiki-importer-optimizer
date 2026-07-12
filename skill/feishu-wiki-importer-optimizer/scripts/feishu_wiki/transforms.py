"""飞书 XML 的富文本清洗、Emoji 重排与评分卡标准化。"""

import re
import sys

try:
    from bs4 import BeautifulSoup, NavigableString, Tag
except ImportError:
    sys.stderr.write(
        "\n[ERROR] 缺少依赖 beautifulsoup4。\n"
        "请先运行本目录下的 setup.sh 初始化隔离环境，或手动安装 requirements.txt。\n\n"
    )
    sys.exit(2)


RED = "rgb(216,57,49)"
EXCLUDED_PUNCT_TAGS = {"whiteboard", "code", "pre", "latex"}
_EMOJI_RANGES = chr(0x1F000) + "-" + chr(0x1FAFF) + "☀-⟿" + chr(0xFE0F)
EMOJI_PATTERN = re.compile("[%s]" % _EMOJI_RANGES)
_CJK_FIRST = "一"
_CJK_LAST = "龥"
HALF_TO_FULL = {
    ":": "：", ",": "，", ";": "；", "?": "？",
    "!": "！", "(": "（", ")": "）",
}


def _has_cjk(value):
    return any(_CJK_FIRST <= char <= _CJK_LAST for char in value)


def _is_cjk(char):
    return _CJK_FIRST <= char <= _CJK_LAST


def _fullwidth_if_cjk_adjacent(text):
    chars = list(text)
    result = []
    for index, char in enumerate(chars):
        if char in HALF_TO_FULL:
            previous_is_cjk = index > 0 and _is_cjk(chars[index - 1])
            next_is_cjk = index + 1 < len(chars) and _is_cjk(chars[index + 1])
            result.append(
                HALF_TO_FULL[char] if previous_is_cjk or next_is_cjk else char
            )
        else:
            result.append(char)
    return "".join(result)


def _in_excluded_punct_tag(element):
    parent = element.parent
    while parent is not None:
        if getattr(parent, "name", None) in EXCLUDED_PUNCT_TAGS:
            return True
        parent = parent.parent
    return False


def clean_punctuation(element):
    if isinstance(element, NavigableString):
        if not _in_excluded_punct_tag(element):
            element.replace_with(_fullwidth_if_cjk_adjacent(str(element)))
    elif isinstance(element, Tag):
        if element.name in EXCLUDED_PUNCT_TAGS:
            return
        for child in list(element.children):
            clean_punctuation(child)


def should_strip_red(span_tag):
    text = span_tag.get_text().strip()
    parent = span_tag.parent
    while parent:
        if parent.name == "h2":
            return True
        parent = parent.parent
    if text in [
        "阅读评级", "维度评分", "推荐理由", "推荐理由：", "维度评分：",
        "思想背景：", "核心论点：", "行动实践：", "避坑防坑：",
    ]:
        return True
    if "推荐指数" in text:
        return True
    parent_bold = span_tag.parent
    if parent_bold and parent_bold.name == "b":
        parent_item = parent_bold.parent
        if parent_item and parent_item.name == "li":
            bold_tags = parent_item.find_all("b")
            if bold_tags and bold_tags[0] == parent_bold:
                return True
            if any(
                keyword in text
                for keyword in ["思想背景", "核心论点", "行动实践", "避坑防坑"]
            ):
                return True
    return bool(re.match(r"^[一二三四五六七八九十]+、", text))


def _emoji_at_end(text):
    match = re.search("(" + EMOJI_PATTERN.pattern + r")+\s*$", text.strip())
    return match.group(0).strip() if match else None


def _emoji_at_start(text):
    match = re.search(r"^\s*(" + EMOJI_PATTERN.pattern + ")+", text.strip())
    return match.group(0).strip() if match else None


def reposition_title_emoji(soup):
    title = soup.find("title")
    if not title:
        return False
    text = title.get_text().strip()
    emoji = _emoji_at_end(text)
    if emoji and not _emoji_at_start(text):
        body = re.sub("(" + EMOJI_PATTERN.pattern + r")+\s*$", "", text).strip()
        title.clear()
        title.append("%s %s" % (emoji, body))
        return True
    return False


def reposition_h2_emoji(soup):
    changed = False
    for heading in soup.find_all("h2"):
        text = heading.get_text().strip()
        emoji = _emoji_at_start(text)
        if emoji and not _emoji_at_end(text):
            body = re.sub(
                r"^\s*(" + EMOJI_PATTERN.pattern + r")+\s*", "", text
            ).strip()
            heading.clear()
            heading.append("%s %s" % (body, emoji))
            changed = True
    return changed


def remove_redundant_h1(soup):
    title = soup.find("title")
    heading = soup.find("h1")
    if not title or not heading:
        return False

    def normalize(value):
        value = re.sub(EMOJI_PATTERN, "", value or "")
        value = re.sub(r"\s+", "", value)
        return value.strip("《》【】：:.-_")

    first_content = next(
        (node for node in soup.find_all(True) if node.name != "title"), None
    )
    if first_content == heading and normalize(title.get_text()) == normalize(
        heading.get_text()
    ):
        heading.extract()
        return True
    return False


def distribute_scores(total, star_counts):
    total = max(0.0, min(10.0, float(total)))
    total_stars = sum(star_counts)
    if total_stars == 0:
        return [total, total, total, total]
    target_sum = total * 4
    raw = [(stars / total_stars) * target_sum for stars in star_counts]
    rounded = [max(0.0, min(10.0, round(score, 1))) for score in raw]
    for _ in range(1000):
        discrepancy = round(target_sum - sum(rounded), 1)
        if abs(discrepancy) < 0.05:
            break
        step = 0.1 if discrepancy > 0 else -0.1
        candidates = [
            index
            for index, value in enumerate(rounded)
            if (step > 0 and value < 10.0) or (step < 0 and value > 0.0)
        ]
        if not candidates:
            break
        selected = max(
            candidates, key=lambda index: (raw[index] - rounded[index]) * step
        )
        rounded[selected] = round(rounded[selected] + step, 1)
    return rounded


def digitize_scorecard(soup):
    card = soup.find("callout", attrs={"emoji": "⭐"})
    if not card:
        return False
    paragraphs = card.find_all("p")
    if len(paragraphs) < 3:
        return False
    rating, dimension, reason = paragraphs[0], paragraphs[1], paragraphs[2]

    total_rating = 9.0
    match = re.search(r"([0-9\.]+)\s*/\s*10", rating.get_text())
    if match:
        total_rating = float(match.group(1))
    else:
        match = re.search(
            r"(?:评级|评分|指数|分数)\s*[：:\s]\s*([0-9\.]+)", rating.get_text()
        )
        if match:
            total_rating = float(match.group(1))
    total_rating = max(0.0, min(10.0, total_rating))
    rating.clear()
    rating.append(_bold("阅读评级"))
    rating.append("：%.1f / 10.0" % total_rating)

    dimension_text = dimension.get_text()
    rules = [
        ("💡 思想启发度", [r"💡\s*思想启发度", r"思想启发度", r"思想/原创度", r"思想启发", r"思想/原创"]),
        ("🌱 易操作性", [r"🌱\s*易操作性", r"易操作性", r"操作/实践性", r"易操作", r"操作/实践"]),
        ("💰 财富增值度", [r"💰\s*财富增值度", r"财富增值度", r"商业/增值度", r"财富增值", r"商业/增值"]),
        ("⏳ 经典程度", [r"⏳\s*经典程度", r"经典程度", r"经典/持久度", r"经典/持久"]),
    ]
    parsed = []
    for _, patterns in rules:
        matched = None
        for pattern in patterns:
            score_match = re.search(
                pattern + r"\s*[：:]\s*([★☆\s]+|[0-9\.]+)(?:\s*/\s*10)?",
                dimension_text,
            )
            if score_match:
                value = score_match.group(1).strip()
                if "★" in value or "☆" in value:
                    matched = ("star", float(value.count("★")))
                else:
                    try:
                        matched = ("numeric", float(value))
                    except ValueError:
                        pass
                break
        if matched:
            limit = 10.0 if matched[0] == "numeric" else 5.0
            parsed.append((matched[0], max(0.0, min(limit, matched[1]))))
        else:
            parsed.append(("missing", None))

    if any(kind == "numeric" for kind, _ in parsed):
        scores = [
            value if kind == "numeric" else value * 2.0 if kind == "star" else total_rating
            for kind, value in parsed
        ]
    else:
        present = [value for kind, value in parsed if kind == "star"]
        fallback = sum(present) / len(present) if present else total_rating / 2.0
        scores = distribute_scores(
            total_rating,
            [value if kind == "star" else fallback for kind, value in parsed],
        )
    dimension.clear()
    dimension.append(_bold("维度评分"))
    dimension.append(
        "：" + " | ".join(
            "%s：%.1f" % (rules[index][0], scores[index])
            for index in range(4)
        )
    )

    clean_reason = re.sub(
        r"^(🗣️)?\s*(推荐理由)?[：:]\s*", "", reason.get_text()
    ).strip()
    reason.clear()
    reason.append("🗣️ ")
    reason.append(_bold("推荐理由"))
    reason.append("：" + clean_reason)
    return True


def _bold(text):
    tag = BeautifulSoup("", "html.parser").new_tag("b")
    tag.string = text
    return tag
