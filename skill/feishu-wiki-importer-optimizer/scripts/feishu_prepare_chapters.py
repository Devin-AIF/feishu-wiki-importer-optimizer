#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
飞书知识库文档制作工具 - 章节本地预处理与无损格式化 (Prepare)
功能：
  1. 读取本地 Markdown 章节原文文件；
  2. 实现“行尾非结束标点”智能段落重组拼缝算法，消除硬换行；
  3. 自动检测图片引用语法并调用飞书 Drive 上传图片，替换为合规的 src=token <img> 标签并嵌入描述 (caption)；
  4. 自动转换 LaTeX 公式（\\(...\\) 与 \\[...\\]）为原生 <latex> 标签；
  5. 自动升级 Markdown 粗体 **重点** 为飞书加粗红色高亮字色格式；
  6. 自动为章节追加“四、 逻辑漏洞审视 ⚠️”，并重排后面的“五、 行动实践清单 ✅”和“六、 完整原文 📝”。
"""

import argparse
import json
import os
import re
import subprocess
import sys
from html import escape
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# 添加当前路径供 lark-cli common 导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from common import atomic_write_json, backup_file
except ImportError:
    atomic_write_json = None
    backup_file = None


IMAGE_LINE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
ALLOWED_REVIEW_TAGS = {"b", "em", "strong"}


def _atomic_save_json(data, path):
    """保持兼容的 JSON 写入接口，优先使用共享的原子写入。"""
    if atomic_write_json:
        atomic_write_json(path, data)
        return
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _safe_caption(text):
    """只保留作为属性值的纯文本，以防 XML 属性注入。"""
    return escape((text or "").strip(), quote=True)


def _sanitize_review_html(text):
    """逻辑审视只允许简单的强调标签，其余内容作为文字输出。"""
    soup = BeautifulSoup(text or "", "html.parser")
    for tag in list(soup.find_all(True)):
        if tag.name not in ALLOWED_REVIEW_TAGS:
            tag.unwrap()
        else:
            tag.attrs = {}
    return str(soup)


def _image_cache_key(img_rel_path, md_dir):
    return os.path.normcase(_resolve_local_image_path(img_rel_path, md_dir))


def _resolve_local_image_path(img_rel_path, md_dir):
    """仅允许 Markdown 目录内的本地图片。

    避免来自不受信任 Markdown 的 URL、绝对路径或 ``..`` 路径被当作本地文件上传至飞书。
    """
    value = (img_rel_path or "").strip()
    parsed = urlparse(value)
    if not value or parsed.scheme or parsed.netloc or os.path.isabs(value):
        raise ValueError(f"仅支持本地相对图片路径: {img_rel_path!r}")
    root = os.path.realpath(md_dir)
    candidate = os.path.realpath(os.path.join(root, value))
    if os.path.commonpath([root, candidate]) != root:
        raise ValueError(f"图片路径超出 Markdown 目录: {img_rel_path!r}")
    if not os.path.isfile(candidate):
        raise ValueError(f"图片文件不存在: {img_rel_path!r}")
    return candidate


def _image_dimensions(img_rel_path, md_dir):
    """最佳努力获取宽高；Pillow 未安装或文件不可读时安全降级。"""
    try:
        from PIL import Image
        with Image.open(_resolve_local_image_path(img_rel_path, md_dir)) as image:
            return image.width, image.height
    except Exception:
        return None, None

def load_json_file(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json_file(data, path):
    _atomic_save_json(data, path)

def upload_image(img_rel_path, md_dir, cache, cache_path):
    local_path = _resolve_local_image_path(img_rel_path, md_dir)
    cache_key = _image_cache_key(img_rel_path, md_dir)
    img_filename = os.path.basename(img_rel_path)
    # 兼容旧版只按 basename 缓存的 uploaded_images.json；新写入使用完整路径。
    if cache_key in cache:
        return cache[cache_key]
    has_stable_cache = any(os.path.isabs(str(key)) for key in cache)
    if img_filename in cache and not has_stable_cache:
        # 第一次读取旧格式时迁移到稳定路径键；后续不会让不同目录的同名图片串用 token。
        cache[cache_key] = cache[img_filename]
        save_json_file(cache, cache_path)
        return cache[cache_key]

    print(f"Uploading image to Drive: {img_rel_path} ...")
    # lark-cli 使用相对 md_dir 路径，以保持原有用法兼容；路径已在上方受到约束。
    upload_path = os.path.relpath(local_path, os.path.realpath(md_dir))
    cmd = ["lark-cli", "drive", "+upload", "--file", upload_path]
    try:
        # [SECURITY] 列表执行官方 CLI，cwd在 md_dir 路径（安全模式，无 shell=True）
        res = subprocess.run(  # noqa: S603
            cmd, cwd=md_dir, capture_output=True, text=True, check=True, timeout=120
        )
        data = json.loads(res.stdout)
        if data.get("ok") and "data" in data:
            file_token = data["data"]["file_token"]
            cache[cache_key] = file_token
            save_json_file(cache, cache_path)
            print(f"  Successfully uploaded -> file_token: {file_token}")
            return file_token
        else:
            print(f"  Upload failed: {res.stdout}")
    except Exception as e:
        print(f"  Exception during upload: {e}")
    return None

def md_to_html(md_content, md_dir, cache, cache_path):
    lines = md_content.split("\n")
    html_elements = []

    current_paragraph = []
    END_PUNCTUATION = {"。", "！", "？", "；", "”", "：", ":", "!", "?", ";", "."}

    i = 0
    while i < len(lines):
        line = lines[i]
        line_str = line.strip()

        # 1. 过滤一级标题
        if line_str.startswith("# "):
            i += 1
            continue

        # 2. 处理图片及图片描述。必须是完整的 Markdown 图片行，不能误吃掉
        # 以 ')' 结尾的普通文本或链接。
        img_match = IMAGE_LINE_RE.fullmatch(line_str)
        if img_match:
            if current_paragraph:
                html_elements.append(process_paragraph("".join(current_paragraph)))
                current_paragraph = []

            alt = img_match.group(1)
            img_path = img_match.group(2).strip()
            caption_text = ""
            # 如果下一行是图片标注描述，如 *图 1-2 ...*
            if (i + 1 < len(lines)
                    and lines[i + 1].strip().startswith("*图")
                    and lines[i + 1].strip().endswith("*")):
                caption_text = lines[i + 1].strip().strip("*")
                i += 1

            try:
                file_token = upload_image(img_path, md_dir, cache, cache_path)
            except ValueError as exc:
                file_token = None
                upload_error = str(exc)
            else:
                upload_error = None
            if file_token:
                img_filename = escape(os.path.basename(img_path), quote=True)
                width, height = _image_dimensions(img_path, md_dir)
                attrs = [f'src="{escape(file_token, quote=True)}"', f'name="{img_filename}"']
                if width and height:
                    attrs.extend([f'width="{width}"', f'height="{height}"'])
                caption = caption_text or alt
                if caption:
                    attrs.append(f'caption="{_safe_caption(caption)}"')
                html_elements.append(f'<img {" ".join(attrs)}/>')
            else:
                html_elements.append(
                    f'<p><b>[图片上传失败: {escape(upload_error or img_path)}]</b></p>'
                )
            i += 1
            continue

        # 3. 处理空行
        if not line_str:
            if current_paragraph:
                html_elements.append(process_paragraph("".join(current_paragraph)))
                current_paragraph = []
            i += 1
            continue

        # 4. 处理二级/三级小标题
        if line_str.startswith("## ") or line_str.startswith("### "):
            if current_paragraph:
                html_elements.append(process_paragraph("".join(current_paragraph)))
                current_paragraph = []
            title_text = line_str.lstrip("#").strip()
            html_elements.append(f"<p><b>{escape(title_text)}</b></p>")
            i += 1
            continue

        # 5. 处理引用块
        if line_str.startswith(">"):
            if current_paragraph:
                html_elements.append(process_paragraph("".join(current_paragraph)))
                current_paragraph = []
            quote_text = line_str.lstrip(">").strip()
            html_elements.append(process_paragraph(quote_text, is_quote=True))
            i += 1
            continue

        # 6. 处理常规文本段落重组
        if current_paragraph:
            prev_line = current_paragraph[-1]
            prev_char = prev_line.strip()[-1] if prev_line.strip() else ""
            if prev_char in END_PUNCTUATION:
                # 前行有句尾标点，冲洗并另起新段
                html_elements.append(process_paragraph("".join(current_paragraph)))
                current_paragraph = [line_str]
            else:
                # 前行未结束，缝合
                if prev_char.isalnum() and line_str[0].isalnum():
                    current_paragraph.append(" " + line_str)
                else:
                    current_paragraph.append(line_str)
        else:
            current_paragraph = [line_str]
        i += 1

    if current_paragraph:
        html_elements.append(process_paragraph("".join(current_paragraph)))

    return "\n".join(html_elements)

def process_paragraph(text, is_quote=False):
    # 先转义原文，再只恢复由本脚本明确生成的安全标签。
    text = escape(text)
    # 替换 LaTeX 公式
    text = re.sub(r'\\\((.*?)\\\)', r'<latex>\1</latex>', text)
    text = re.sub(r'\\\[(.*?)\\\]', r'<latex>\1</latex>', text)
    # 替换加粗为红字粗体
    text = re.sub(
        r'\*\*(.*?)\*\*',
        r'<b><span text-color="rgb(216,57,49)">\1</span></b>',
        text,
    )
    # 替换脚注
    text = re.sub(
        r'\[\^(.*?)\]',
        r'<b><span text-color="rgb(216,57,49)">[\1]</span></b>',
        text,
    )

    if is_quote:
        return f'<p><em><b>{text}</b></em></p>'
    else:
        return f'<p>{text}</p>'

def update_chapter_json(json_path, md_path, logic_reviews, cache, cache_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    # 1. 将 MD 全文无损转换为 HTML
    full_text_html = md_to_html(md_content, os.path.dirname(md_path), cache, cache_path)

    # 2. 用 BeautifulSoup 对 XML 结构重组
    soup = BeautifulSoup(data["xml"], "html.parser")

    # 修正现有 H2 序列和标题
    h2s = soup.find_all("h2")
    for h2 in h2s:
        if "四、 行动实践清单" in h2.text:
            h2.string = "五、 行动实践清单 ✅"

    # 重新定位
    h2s = soup.find_all("h2")

    # 插入“四、 逻辑漏洞审视 ⚠️”
    opinions_h2 = None
    for h2 in h2s:
        if "三、 核心观点解读" in h2.text:
            opinions_h2 = h2
            break

    if opinions_h2:
        opinions_ul = opinions_h2.find_next_sibling("ul")
        if opinions_ul:
            existing_review = opinions_ul.find_next_sibling("h2")
            if not (existing_review and "四、 逻辑漏洞审视" in existing_review.text):
                review_h2 = soup.new_tag("h2")
                review_h2.string = "四、 逻辑漏洞审视 ⚠️"

                callout = soup.new_tag("callout", emoji="💡")
                callout["background-color"] = "light-red"
                callout["border-color"] = "red"

                p_title = soup.new_tag("p")
                p_title.append(BeautifulSoup("<b>逻辑漏洞审计：</b>", "html.parser"))
                callout.append(p_title)

                ul = soup.new_tag("ul")
                for rev_text in logic_reviews:
                    li = soup.new_tag("li")
                    li.append(BeautifulSoup(_sanitize_review_html(rev_text), "html.parser"))
                    ul.append(li)
                callout.append(ul)

                opinions_ul.insert_after(review_h2)
                review_h2.insert_after(callout)

    # 3. 将最后一个 H2 改名为 “六、 完整原文 📝” 并灌入完整段落
    h2s = soup.find_all("h2")
    if not h2s:
        raise ValueError(f"章节 JSON 缺少 <h2> 结构，拒绝覆盖: {json_path}")
    last_h2 = h2s[-1]
    last_h2.string = "六、 完整原文 📝"

    # 清空该标题后的多余老段落
    curr = last_h2.next_sibling
    while curr:
        nxt = curr.next_sibling
        if curr.name in ("p", "grid", "callout", "div", "img") and curr.get_text(strip=True) != "":
            curr.decompose()
        curr = nxt

    # 追加段落
    full_text_soup = BeautifulSoup(full_text_html, "html.parser")
    for element in reversed(full_text_soup.contents):
        if element.name:
            last_h2.insert_after(element)

    # 4. 写回 JSON
    data["xml"] = str(soup)
    if backup_file:
        backup_file(json_path)
    _atomic_save_json(data, json_path)

def main():
    parser = argparse.ArgumentParser(description="飞书知识库章节本地处理与无损格式化工具")
    parser.add_argument("--md-dir", required=True, help="本地原稿 Markdown 目录")
    parser.add_argument("--json-dir", required=True, help="临时章节 JSON 文件存储目录")
    parser.add_argument("--chapters-nodes", required=True, help="章节大纲 chapters_nodes.json 配置文件路径")
    parser.add_argument("--uploaded-images", required=True, help="图片上传缓存 JSON 路径")

    args = parser.parse_args()

    if not os.path.exists(args.chapters_nodes):
        print(f"Error: 大纲配置文件不存在: {args.chapters_nodes}")
        sys.exit(1)

    with open(args.chapters_nodes, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    img_cache = load_json_file(args.uploaded_images)

    print("Starting chapters local processing & formatting workflow...")

    # 对大纲中每个非总纲的具体正文章节进行转化处理
    for idx, item in enumerate(mapping):
        filename = item["filename"]
        title = item["title"]

        # 排除总纲节点本身
        if filename == "50-总纲.md" or "总纲" in title:
            continue

        md_path = os.path.join(args.md_dir, filename)
        # 根据大纲中的文件名索引（前缀数字）映射到具体的 chapter_X.json
        prefix = filename.split("-")[0]
        try:
            chapter_idx = int(prefix) - 1
        except ValueError:
            print(f"Skip file with non-standard numeric prefix: {filename}")
            continue

        json_path = os.path.join(args.json_dir, f"chapter_{chapter_idx}.json")

        if not os.path.exists(md_path):
            print(f"Warning: 本地 MD 缺失，跳过: {md_path}")
            continue
        if not os.path.exists(json_path):
            print(f"Warning: 临时 JSON 缺失，跳过: {json_path}")
            continue

        print(f"\nProcessing [{chapter_idx+1:02d}] {filename} -> chapter_{chapter_idx}.json...")

        # 提取该章节的逻辑漏洞审视内容，如果没有则提供通用的兜底
        logic_reviews = item.get("logic_reviews", [
            "<b>结论边界缺失：</b>本章节内容偏重理论模型推导，在现实操作中，由于交易摩擦损耗、高昂的利息支出及家庭应急现金流的要求，策略敞口边界应更加审慎客观。"
        ])

        update_chapter_json(json_path, md_path, logic_reviews, img_cache, args.uploaded_images)

    print("\nAll chapters successfully formatted and saved to JSON files!")

if __name__ == "__main__":
    main()
