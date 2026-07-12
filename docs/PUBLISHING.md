# Skill Hub 平台 Skill 发布规范与编写指南 (Skill Hub Publishing Guideline)

> **本仓库发布控制（优先于下文历史说明）**：发布时只能使用
> `python3 tools/build_release.py` 生成的 allowlist ZIP。真实映射、章节原文、
> 图片、缓存、验证脚本、历史归档和虚拟环境一律不进入 Skill 包；`*.example.json`
> 必须是合成示例，不能包含任何真实飞书资源标识或本机绝对路径。

本指南针对在 **Skill Hub 平台**（AI Agent 技能分发中心）发布和分享自定义 Skill 时的核心申报格式、目录结构及质量审计标准进行规范说明，以确保发布的 Skill 能够被其他 Agent 高效理解并精准激活。

---

## 📂 1. Skill 发布包的标准目录结构

一个可以在 Skill Hub 平台无缝发布并被 Agent 加载的 Standard Skill 包必须遵循以下目录布局：

```text
my-custom-skill/                        # Skill 包根目录（推荐使用 kebab-case 命名）
├── SKILL.md                            # [必填] 技能定义的主控文档（含元数据与运行契约，唯一权威源）
├── agents/openai.yaml                  # [推荐] UI 元数据
├── scripts/                            # 可执行代码、依赖声明和体检脚本
├── references/                         # 按需加载的操作说明
└── assets/                             # 仅可公开的模板 / 合成示例
```

> **数据隔离**：真实 `chapters_nodes.json`、`mermaid_maps.json`、章节正文、图片、快照、缓存和验证配置必须存放在包外私有工作区。Skill 仅可提供 `*.example.json` 合成示例；脚本必须允许通过参数或环境变量定位私有数据。

---

## 📝 2. `SKILL.md` 主控文档的标准定义格式

`SKILL.md` 是 Skill Hub 的核心入口。它**必须**以符合 YAML 规范的 Frontmatter（元数据头部）开头，后接结构清晰的 markdown 运行指南：

```markdown
---
name: feishu-wiki-importer-optimizer     # [必填] 全局唯一的 Skill 标识，仅允许英文、数字、中划线
version: 3.0                             # [必填] 语义化版本号（须与本技能实际 version 保持一致）
description: 把本地文档交给 AI 按结构解读（打分/脑图/待办/原文）后，批量建档到飞书知识库并统一排版打磨的工具包：并发建档、原生导航挂载、重点 RGB 标红、Emoji 规范、全角标点净化、白板脑图防丢重绘。脚本负责「建档 + 打磨」；文档解读（生成结构化内容与脑图数据源）由 AI 助手按本规范页面模板完成。
author: Devin
tags: [feishu, wiki, markdown, formatter, automation, rich-text, knowledge-base] # 搜索分类标签
---

# 文档解读 → 飞书知识库 建档与排版技能

## 🎯 技能激活场景 (Activation Triggers)
【声明 Agent 应当在何时加载并执行本技能】
* 当用户要把一批本地 Markdown 文档交给 AI 按页面模板解读（生成评分卡/金句/逻辑脑图/核心观点/行动清单/原文摘录），并批量创建进飞书知识库成为统一排版的阅读页。
* 当用户发现云端文档存在「重点未红字高亮」「脑图空白丢失」「标题/小标题 Emoji 位置不一致」等渲染问题，需要一键打磨修复。
* 当需要在飞书 Wiki 目录下批量创建子页面并自动挂载二级导航。

## 📜 输入输出契约 (Contract & Interface)
* **输入契约**：
  1. `chapters_nodes.json` 章节大纲映射（**由 AI 解读阶段产出**，含 `index`/`title`，建档后回填 Token）。
  2. 空间 ID (`space_id`) 与父挂载节点标识 (`parent_node_id`)。
* **输出契约**：
  在云端指定飞书 Wiki 目录下自动生成具备原生级联导航、全文重点标红加粗、全景脑图正确渲染的高品质文献智识库页面。

## ⚠️ 绝对底线限制 (Hard Constraints)
【Agent 在执行该技能时绝不可违反的物理铁律】
1. **富文本嵌套铁律**：加粗与字色必须严格写为 `<b><span text-color="rgb(216,57,49)">...</span></b>`。顺序颠倒或使用不支持的命名色 `red` 会导致格式直接被飞书云端过滤丢弃。
2. **白板防丢铁律（两阶段）**：`overwrite` 提交前必须剥离 `<whiteboard>` 的 `id` 和 `token`（仅留 `type="mermaid"`）强制云端重分配；`overwrite` 成功后必须再从响应 `new_blocks` 抓取白板 `block_token`，二次调用 `whiteboard +update` 把 Mermaid 源码渲染写入——**只剥离不重渲染会导致网页端画板空白**。该逻辑只能在 `common.py` 唯一实现，全工具共用。
3. **禁用 sup 上标**：飞书 API 不解析 `<sup>` 标签，引用脚注必须使用 `<b><span text-color="rgb(216,57,49)">[数字]</span></b>` 代替。
4. **标点净化安全边界**：半角→全角仅对「紧邻中文」的标点生效；整体跳过 `whiteboard`/`code`/`pre`/`latex` 标签，避免破坏中英双栏英文原文、公式括号与 Mermaid 源码。
```

---

## 🏆 3. Skill Hub 发布时的“五星质量审计标准” (Quality Audit Standards)

为了保证发布的 Skill 在 Skill Hub 上获得推荐并被 Agent 100% 正确调用，发布前需进行以下五维自检：

### ⭐ 维度一：场景边界的“单一职责原则” (Single Responsibility)
* **标准**：一个 Skill 只干一件事并干到极致。严禁把“飞书导入”和“数据爬取/翻译”混在一个 Skill 中。如果需要翻译，应当声明其依赖于另一个特定的翻译 Skill。
* **要求**：在 `SKILL.md` 中以 negative statements 标明不干什么（例如：“*本技能不负责文献的多语言翻译，只负责结构化文本与脑图的格式对齐*”）。

### ⭐ 维度二：运行依赖的“沙箱与零依赖原则” (Zero-Dependency)
* **标准**：除了系统必备的命令（如本次真实依赖的 `lark-cli`，飞书官方 CLI，本工具所有云端读写的真正执行者）外，Skill 附带的脚本应尽量减少第三方库依赖，优先在隔离环境瞬间跑通。
* **要求**：如果使用了 Python 脚本，优先选用原生标准库（如 `urllib` 替换 `requests`）。若确需第三方库（如本技能用 `beautifulsoup4` 做健壮的飞书 XML DOM 解析），**必须**在包内附带 `requirements.txt` + `setup.sh`（自动建 `.venv` 隔离安装，不污染用户环境）+ `doctor.sh`（一键体检依赖与登录态）。绝不硬编码依赖版本到系统全局。

### ⭐ 维度三：配置与路径的“环境无关原则” (Environment Agnostic)
* **标准**：代码中绝对不允许出现写死的绝对物理路径（如 `/Users/xxx/Downloads/...`）。
* **要求**：所有本地配置文件读取必须采用 `os.path.dirname(os.path.abspath(__file__))` 动态相对定位，保证 Skill 被其他开发者下载到任意目录、任意系统均能立即执行。

### ⭐ 维度四：API 的“幂等性与频控友好性原则” (Idempotence & Rate-Limit Friendly)
* **标准**：Agent 在调用该 Skill 时极易进行重复运行测试，所以 Skill 必须天生具备防重、幂等能力。
* **要求**：对云端写操作（如 Wiki 节点创建）必须有去重检测。对于高频并发调用，必须配置指数级退避重试（Exponential Backoff）和并发度限流（建议并发限额 5 个 Worker 以内），防止遭飞书频控阻断。

### ⭐ 维度五：富文本渲染的“SaaS 兼容性原则” (SaaS Rendering Compatibility)
* **标准**：输出的多媒体 XML/HTML 代码必须通过严格的 SaaS 解析验证。
* **要求**：在 Skill 中声明所有富文本标记的闭合规范。对于表格必须包含 `<colgroup>` 定义列宽，对于连线图示必须净化冒号 `:`，规避解析器 Crash 风险。
