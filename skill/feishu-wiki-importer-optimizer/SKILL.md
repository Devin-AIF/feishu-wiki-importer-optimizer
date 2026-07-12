---
name: feishu-wiki-importer-optimizer
description: 把本地文档交给 AI 按结构解读（打分 / 脑图 / 待办 / 原文）后，批量建档到飞书知识库并统一排版打磨的工具包：一键并发建档、原生导航挂载、重点 RGB 标红、Emoji 规范、全角标点净化、白板脑图防丢重绘。脚本负责「建档 + 打磨」；文档解读（生成结构化内容与脑图数据源）由 AI 助手按本文件页面模板完成。
---

# 文档解读 → 飞书知识库 建档与排版技能 (Doc-Interpreter → Feishu Wiki Builder)

> 本文件是**唯一权威规范源（single source of truth）**。所有脚本行为、排版铁律、API 避坑均以此为准；各版本迭代中沉淀的经验已固化进下文各对应条款，不再以独立追加段落形式存在，避免规范与实现漂移（挂一漏万）。

## 🎯 技能激活场景 (Activation Triggers)

* 把一批本地 Markdown 文档交给 **AI 按本文件页面模板解读**（生成评分卡 / 金句 / 逻辑脑图 / 核心观点 / 行动清单 / 原文摘录），并**批量创建进飞书知识库**成为统一排版的阅读页。
* 发现云端文档存在「重点未红字高亮」「脑图空白丢失」「标题/小标题 Emoji 位置不一致」等渲染问题，需要一键打磨修复。
* 需要在飞书 Wiki 目录下批量创建子页面并自动挂载二级导航。

> ⚠️ **范围与角色声明**：本 Skill 是「**解读 → 建档 → 打磨**」整条链路的工具包，但三件事分工不同：
> - **解读（AI 助手负责）**：按 §页面结构模板把本地文档转成结构化内容，并产出 `config/outline.json`（大纲，不含 Token）与 `generated/mermaid_maps.json`（键为稳定 `chapter_id`）。这一步由 AI 助手执行，**不在脚本内**；产物只能放入私有运行工作区，不能放入本 Skill。
> - **建档 + 打磨（本包脚本负责）**：`create-nodes` / `update-nav` 把解读结果落进飞书，`polish` / `restore-wb` 落实排版铁律。**脚本不直接解析 PDF/OCR**，也不自己做「文档理解」；它消费 AI 解读的产物。
> - 页面正文由 AI 按 §页面结构模板写成飞书 XML，经脚本 `overwrite_and_render`（底层 `lark-cli docs +update --command overwrite`）灌入已建好的节点；`create-nodes` 仅按大纲创建空标题节点并回填 Token，不导入正文（见 §端到端工作流）。

## 📜 输入输出契约 (Contract & Interface)

* **输入**：私有项目中的 `config/outline.json`、`state/remote_nodes.json` 和 `generated/mermaid_maps.json`；已 `lark-cli auth login` 的会话；经用户确认的空间 ID 与父挂载节点标识。
* **输出**：云端指定 Wiki 目录下具备原生级联导航、全文重点标红加粗、全景脑图正确渲染的高品质文献智识库页面。

## 🧰 工具清单 (Tools)

本包已整合为**单一主命令行** `scripts/feishu_wiki.py`（子命令）。
共享实现按职责位于 `scripts/feishu_wiki/`，`scripts/common.py` 仅保留旧导入兼容：

| 子命令 | 作用 | 关键参数 |
|--------|------|----------|
| `scripts/init_project.py` | 离线创建私有工作区与 `projects/<slug>/` 分层骨架；不访问飞书 | `--workspace/--project/--force` |
| `scripts/migrate_workspace.py` | 离线预检/迁移旧扁平工作区；先 checksum，旧目录只归档 | `--workspace/--project/--apply` |
| `create-nodes` | 合并读取大纲与远端状态，批量建档并只回写 `state/`；带预扫描去重幂等 | `--space/--parent/--dry-run` |
| `update-nav` | 父页面底部挂载飞书原生 `<sub-page-list>` 导航 | `--space/--parent-obj/--parent-node/--dry-run` |
| `polish` | 一站式排版打磨（见 §7 全部规则 + 白板防丢重绘） | `--workers N/--dry-run` |
| `restore-wb` | 仅对白板（Mermaid 脑图）防丢重绘 / 缺失补全 | `--workers N/--dry-run` |
| `prepare` | 将本地 Markdown 合并到已生成的章节 JSON；预检时不上传图片 | `--md-dir/--json-dir/--dry-run` |
| `push` | 按 `chapter_id`/标题强绑定后覆写已确认节点；预检告警默认整批中止 | `--json-dir/--dry-run/--allow-partial` |
| `scripts/feishu_wiki/` | 分层实现：路径/存储、API 封装、富文本、白板、安全覆写 | — |
| `scripts/common.py` | 旧 `from common import ...` 的薄兼容导出层；新代码不得依赖 | 仅兼容 |
| `generated/mermaid_maps.json` | 脑图源码**单一数据源**（键=`chapter_id`） | 不随包发布 |
| `config/outline.json` + `state/remote_nodes.json` | 章节结构与云端状态物理分离 | 不随包发布 |

## 🔒 发布与私有数据边界

本目录是唯一可发布的 Skill 包。它只能包含发布白名单中的
`SKILL.md`、`agents/`、`scripts/`、`references/` 和完全合成的
`assets/*.example.json` / `assets/*.template.json`；严禁把真实章节、课程/书籍原文、
图片、评论、`node_token`/`obj_token`、空间标识、`*.local.json`、`*.bak.json`、
`*.free.json`、快照、缓存、虚拟环境、验证脚本或 Git 元数据带入本目录。

将运行数据存入私有工作区，并在运行前设置：

```bash
export FEISHU_WIKI_WORKSPACE="/secure/path/feishu-wiki-workspace"
```

未设置时，开发仓库优先使用同级 `<repo>.private-workspace`；独立安装时使用用户的
本地状态目录。新项目必须使用 `projects/<slug>/` 分层；项目选择、
权限、Schema 和文件归属见 [`references/project-layout.md`](references/project-layout.md)。
旧扁平工作区的兼容说明见 [`references/runtime-data.md`](references/runtime-data.md)。不要用 Finder 压缩或
仓库根目录上传发布；必须使用开发仓库的 allowlist 发布工具生成制品。

旧扁平布局只作显式兼容读取；新任务不得在 `mappings/` 中继续创建配置。
迁移时先运行 `scripts/migrate_workspace.py` 预检，确认独立备份后才追加 `--apply`。

## ⚖️ 内容授权与最小化

仅处理用户拥有、获得授权或可合法处理的文档与图片。第三方书籍、课程、评论和
网页内容不得因为“私有工作区”而自动获得再分发权；不得把它们放入 Git、Skill 包、
示例、日志、测试夹具或公开问题单。处理第三方材料时，只将完成任务所需的最少内容
写入用户授权的私有飞书空间，并先获得用户对结构和写入范围的确认。

## 🔴 核心元规范 (Five Engineering Meta-Rules)

所有执行飞书导入的 Agent / 开发者在架构与工程改动时，必须死守以下四条高维规则（它们优先于下文任何具体条款）：

1. **幂等性与数据防脏铁律 (Idempotence)**：创建/更新操作必须具备幂等。建档前先拉取父目录全量子节点并复用同名节点（见 `api_get_nodes`）；`overwrite` 优先基于原 Block 局部重写，禁止盲目全量覆盖。
2. **渐进式修改与非破坏性增量律 (Incremental)**：禁止对未定义区域做大范围模糊正则替换（防跨标签吞噬）。字色高亮须先用精确节点截断隔离，只在受控子区域局部处理（见 §7.1 安全正则）。
3. **富文本安全解析与兜底避让律 (Rich-Text Safety)**：飞书 API 不解析非标 HTML 标签（如 `sup`/`sub`）。遇到不兼容标签必须主动转写为飞书支持的替代样式（如脚注 `[1]` → `<b><span text-color="rgb(216,57,49)">[1]</span></b>`），严禁把非标标签直接写入 XML，从源头拦截 `invalid document structure` 报错。
4. **脚本便携与零环境假设规范 (Portable)**：禁止硬编码任何绝对物理路径或特定用户临时路径；资源标识经 `--参数` 或交互式 `input()` 传入并做缺失校验；依赖经 `scripts/setup.sh` 在私有运行工作区隔离安装。
5. **大纲确认与方案前置规约 (Design Validation First)**：针对任何新书籍/新专栏的导入与解读，在启动任何自动化建档或正文解读流程前，**必须先为用户输出至少两套知识库层级及大纲结构拆解方案**（明确指出默认推荐方案、各方案的优缺点及层级分类逻辑），等待用户确认完毕并选定方案后，方可进行细化和自动化执行，彻底避免结构性返工。


## 🧱 页面结构模板 (Page Structure Templates)

> 知识库结构由 **4 类节点**组成（深度 3 层：L0→L1→L2）：根/索引页 (L0) → 总纲页 (L1a Overview) + 二级分类页 (L1b Category) → 文章页 (L2)。「总纲页」是根节点下的一个独立【总纲】子页，并非根本身。各类型模板如下（生成内容时遵循，脚本打磨时校验）：

### 1. 知识库根 / 索引页（Root / Index Node，即分享 URL 指向的顶层文档）
* 角色：**着陆页 / 合集入口**，不是内容页。**建档或推送工具包应自动对用户提供的最上级根节点页面本身进行正文填充与覆写，使其包含合集背景、核心导航及章节/主题直接跳转指引。**
* 典型章节：`<h2>关于本合集 📖</h2>`、`<h2>学习与导航入口 🧭</h2>`、`<h2>文集九大主题分类指引 📂</h2>`（或主题指引）。
* 富文本：重点句 `<b><span text-color="rgb(216,57,49)">...</span></b>` 标红、`<callout>` 提示卡。
* **导航与层级一致性铁律**：**严禁在知识库 L0 根节点页面底部直接挂载 `<sub-page-list>` 或使用 `update-nav` 子页面导航！** 这会导致大标题序号断裂和重复目录（如“五、子页面导航”）。根页面必须使用 `<ul>` 与 `<cite>` 原生组件手工编织分类指引进行显式/隐式导航，以保证主页 Landing Page 的纯正性与标题层级的一致性（一、二、三...）。
* **不强制白板**；脚本 `polish`/`restore-wb` 对其为「无白板 → 跳过」，属正常。

### 2. 总纲总览页（Overview Node，【总纲】子页）
* `<h2>一、 全书思维全景图 📊</h2>` → `<whiteboard type="mermaid">` 大一统脑图（**强制**，见 §脑图规范）。
* `<h2>二、 核心投资哲学 🏆</h2>` → 列表或浅黄 `<callout emoji="🏆">`。
* `<h2>三、 📂 思想六大板块横向对比</h2>` → `<grid>` + `<column width-ratio>`（4 列各 `0.25`、6 列各 `0.166667`）。
* `<h2>四、 👑 全书必读神作 Top 10</h2>` → 带 `👑` 的 `<callout>` 评分列表。**列表中的每一个推荐条目必须使用飞书原生引用标签 `<cite doc-id="..." file-type="docx" title="章节名称" type="doc"></cite>` 引用实际的文章子页面，严禁只输出纯文本，以确保能正确产生对应跳转文档链接。**
* `<h2>五、 二级分类导航</h2>` → 原生 `<sub-page-list>`（由 `update-nav` 自动挂载）。

### 3. 二级分类目录页面（Category Node，6 个）
* 典型章节：`<h2>主题简介 📂</h2>`、`<h2>本版核心推荐文章 👑</h2>`、`<h2>子文档目录指引 🧭</h2>`。
* **导航方式：原生 `<sub-page-list>`**（由 `update-nav` 挂载，Feishu 自动渲染子节点列表）。
* **不强制白板**；仅主题介绍 + Top3 推荐 + `<sub-page-list>`。

### 4. 具体文章页面（Leaf / Article Node）
按以下模块依次排版：
* 顶部 `<callout emoji="⭐" background="light-blue">` 评分卡（含总评级 + 四维评分 + 推荐理由）。**四维评分的指标名称必须严格规范统一为：💡 思想启发度、🌱 易操作性、💰 财富增值度、⏳ 经典程度。任何遗留的历史变体指标名称（如《财富自由之路》中旧有的“思想/原创度、操作/实践性、商业/增值度、经典/持久度”）必须被自动解析与映射到这四个标准指标中。**
* 三阶阅读导航锚点（极速快餐 / 逻辑漫游 / 硬核精读）。
* 一、 本篇金句 💡（`<callout emoji="💡">`）；二、 深度逻辑图示 🎨（`<whiteboard type="mermaid">`，**强制**）；三、 核心观点解读 💡（`<ul>`）；四、 逻辑漏洞审视 ⚠️（置于 `<callout emoji="💡">` 警示框，红/黄底 + `⚠️`/`💡`）；五、 行动实践清单 ✅（`<checkbox>`）；六、 原文节选 / 完整原文 📝。仅当用户拥有或明确获得完整再现、上传和云端存储的授权时，才可无损导入全文；否则只写入获得授权的节选、摘要或用户提供的可公开内容。图片、LaTeX 和加粗格式应保留在用户授权范围内；本地图片上传后使用原生 `<img src="file_token" width="宽" height="高" caption="说明" />`，避免外部 URL 与尺寸失真。
* **段落失衡强制截断**：双语双栏左右累计字数差 >50% 或 >500 字时，强制闭合当前 Grid 并开启新 Grid 重新对齐。

## 🧠 脑图（白板 Mermaid）规范

> **脑图对「文章页 (L2) 与总纲页 (L1)」为强制项，对「根页 (L0) 与二级分类页 (L1b)」不强制。** 缺失强制项即视为不合格交付。脚本打磨时（特别是 `restore-wb` / `polish` 的 `process_whiteboards()`）会校验；若期望有脑图却无数据，将打印 **`[WARN]`** 显式告警，绝不再静默遗漏。

### 各节点类型的脑图约束（对照页面结构模板）

| 节点类型 | 是否强制脑图 | 落点 | 说明 |
|----------|--------------|------|------|
| **根/索引页 (L0 Root)** | ❌ 不强制 | — | 着陆页，无白板属正常；脚本跳过。 |
| **总纲总览页 (L1 Overview)** | ✅ 强制 | `<h2>一、 全书思维全景图 📊</h2>` 下的 `<whiteboard type="mermaid">` | 大一统合集脑图；私有 `mermaid_maps.json` 按总纲的 `chapter_id` 提供源码，脚本可防丢重绘 / 缺失补全。 |
| **二级分类页 (L1 Category)** | ❌ 不强制 | — | 仅主题介绍 + Top3 推荐 + `<sub-page-list>`，无需白板。 |
| **文章页 (L2 Leaf)** | ✅ 强制 | `<h2>二、 深度逻辑图示 🎨</h2>` 下的 `<whiteboard type="mermaid">` | 单篇思想脉络脑图。脚本会在此标题后自动插入；若文档已有白板则仅重绘。 |

### 脑图源码供应规则（mermaid_maps.json 单一数据源）
* 每一篇**文章页**的脑图 Mermaid 源码应存在于 `mermaid_maps.json`，键必须为大纲中的稳定 `chapter_id`；读取器仅为旧项目保留标题键兼容。
* **匹配已支持 Emoji 前缀标题**：真实文章标题形如 `📘 读书笔记 #3：如何开始...`，`find_mermaid_key()` 会从标题中**抽取 `#N` 数字令牌**查表（内容无关，适用于任意文档集）——既规避 `#3` 误命中 `#33` 的子串 Bug，也兼容 `🛡️`/`📈`/`🎯` 等 Emoji 前缀导致的 `startswith` 失效。总纲页则以**精确标题**作为键。
* 本包仅随附 `assets/mermaid_maps.example.json` 合成示例；生产使用时应在私有工作区按实际文章页补全 `mermaid_maps.json`。
  * 若本地 `.md` 导入时已携带 Mermaid 代码块（推荐做法），白板在导入阶段即生成，`mermaid_maps.json` 仅用于「白板丢失后的缺失补全」；
  * 若 `.md` 不含 Mermaid、需要从零补全所有文章脑图，则**必须**把全部文章页脑图填入 `mermaid_maps.json`（键=`chapter_id`）。
* 若文章页含「深度逻辑图示 / 全景图 / 思维导图 / 脑图」标题但 `mermaid_maps.json` 无对应键 → 脚本告警 `[WARN] ... 该页将无脑图`，需补条目后再跑。
* 若文章页连脑图章节都缺失 → 脚本告警 `[WARN] 未检测到 <whiteboard> 也未找到含脑图标题的 <h2>`，提示可能为漏章节。

### ⚠️ Mermaid 编译器兼容性与防错规约
* **特殊字符加引号**：在生成脑图 Mermaid 源码时，严禁直接在节点文本中使用未加引号的冒号 `:`、斜杠 `/`、圆括号 `()` 等特殊字符（例如：`B(策略: 冒号)` 会触发飞书编译器崩溃）。**所有含有特殊字符或标点的节点文本，必须使用双引号 `""` 完整包围**（形如 `B["策略: 冒号"]`）。
* **非核心章节脑图免除**：对于致谢（Acknowledgement）、参考文献/注释（Notes/References）等不含核心投资或策略干货的非正文 Leaf 节点，不强制要求生成或渲染脑图。如果这些页面的 Mermaid 语法出现极难解决的转义冲突，应在 XML 中主动剥离整个 `<h2>二、 深度逻辑图示 🎨</h2>` 标题及对应的 `<whiteboard>` 标签，脚本将自动忽略并以 `[WARN]` 形式通过校验，不会阻断打磨。

### 两阶段写入铁律（防空白画板）
见 §7.6：`overwrite` 前剥离 `<whiteboard>` 的 `id`/`token`；`overwrite` 成功后从 `new_blocks` 抓取 `whiteboard` 的 `block_token` 并二次 `whiteboard +update` 渲染。此逻辑在 `feishu_wiki/whiteboards.py` 与 `feishu_wiki/writer.py` 按职责唯一实现。

## 🎨 排版与富文本铁律 (Layout & Rich-Text Rules)

> 这些规则由 `polish` 子命令在云端 `overwrite` 前自动落实；生成内容时也应主动遵守，减少打磨负担。

### §7.1 富文本嵌套与字色铁律
* 重点句必须写为 `<b><span text-color="rgb(216,57,49)">重点句</span></b>`：**粗体 `<b>` 必须包在字色 `<span>` 外层**；字色必须用 `rgb(216,57,49)`，**禁止**命名色 `red`；顺序颠倒或被过滤为 `red` 会导致飞书云端剥离全部格式（Declassification）。
* **去色红线（严禁染红）**：元数据前缀（`阅读评级`/`维度评分`/`推荐理由`）、结构性大标题、列表序号及引导词前缀（如 `核心论点一`/`思想背景`/`行动实践`）等非正文重点必须保持黑色，由 `should_strip_red()` 自动剥离其红字。
* **安全正则（防跨 Block 吞噬）**：金句框等局部替换必须用排除闭合标签的负向预查正则，例如 `r'<callout([^>]*?emoji="💡"[^>]*?)>((?:(?!</callout>).)*?)</callout>'`，杜绝非贪婪匹配跨到后续 `<whiteboard>` 将其吞噬（曾因此导致脑图全局神秘丢失）。

### §7.2 Emoji 标题位置规范
* **文章题目 `<title>`**：Emoji 必须置**前**（如 `<title>🚀 《示例知识库》...</title>`）。
* **段落小标题 `<h2>`**：Emoji 必须置**后**（如 `<h2>一、 本篇金句 💡</h2>`）。
* 由 `reposition_title_emoji()` / `reposition_h2_emoji()` 自动校正。

### §7.3 首行 `<h1>` 去冗余
* 正文开头若与页面标题重复的 `<h1>` 必须剔除（飞书 `<title>` 已超大号呈现页面标题，重复极累赘）。由 `remove_redundant_h1()` 处理。

### §7.4 标点全角净化（语言 / 公式感知）
* 仅当半角标点**紧邻中文**时才转全角（`,;:?!()` → `，；：？！（）`）；英文 / 拉丁文本中的标点（含中英混排右列、URL 中的 `:`）保持半角，避免误伤英文原文。
* **安全边界保护**：整体跳过 `whiteboard`/`code`/`pre`/`latex` 标签，避免破坏中英双栏右列英文原文、`<latex>` 公式括号、Mermaid 源码。由 `clean_punctuation()` 实现（基于相邻字符判定，不再依赖「整段含中文即全转」）。

### §7.5 LaTeX / 表格 / 图片 / 引用 / Checkbox
* 数学公式一律用飞书原生 `<latex>`（如 `<latex>FV = PV \times (1 + r)^n</latex>`），禁止纯文本拼凑。
* 多行对比数据用 `<table>` + `<colgroup><col width=.../></colgroup>` 固定列宽。
* **禁用 `<sup>` 上标**：脚注用 `<b><span text-color="rgb(216,57,49)">[数字]</span></b>` 替代。
* **图片原生化上传防丢与防白边铁律**：正文 XML 中严禁直接粘贴外部网络图片 URL 地址。所有图片**必须在建档与覆写阶段，通过 API 动态下载到本地并调用 `lark-cli drive +upload` 上传至用户的云空间中**。获取返回的 `file_token` 后，**必须借助 PIL (Pillow) 库读取图片的真实像素宽高 `width` 与 `height`**，将其以 `<img src="file_token" width="宽" height="高" caption="说明文字" />` 的形式填入正文。若 XML 中缺省图片的 width 和 height，飞书云端在首次解析时会默认强制以 1:1 正方形的 `512x512` 盒子进行图片拉伸填充，导致非正方形的图片在高度或宽度上产生极大的多余白边或拉伸畸变。**图片下方的说明文字必须使用原生 caption 属性指定，利用飞书的自带排版在图片下方以精致的斜体灰字居中展现，严禁另起段落 <p> 来手工编写图注，以防在图片和文字间产生过宽的间距。**
* 跨页引用优先用飞书原生 `<cite doc-id="..." file-type="docx" title="..." type="doc">`，替代传统 `<a>`。
* **二级子讲原生卡片导航构建规则**：在周度/月度等聚合（Overview/Week）页面底部挂载级联列表时，**必须在 XML 中使用原生 `<sub-page-list space-id="..." wiki-token="...">` 并子嵌套多行 `<sub-page doc-id="..." file-type="docx" title="..." />` 的标准飞书物理级联列表格式进行拼接**，严禁使用纯文本、普通超链接或空内容的 `sub-page-list` 标签，以呈现最完美的飞书原生页面导流卡片大纲组件。
* **行动清单（Checklist）XML 语法**：行动实践清单必须使用原生的 `<checkbox done="false"><b>加粗行动标题</b>：行动内容说明</checkbox>` 标签进行独立声明。**严禁**将其嵌套在 `<ul>`、`<ol>` 或者是 `<li>` 列表标签内部，否则会导致飞书 XML 格式审查报错或整段内容被云端静默丢弃。
* **Wiki 侧边栏图标 API 限制与手动弥补**：受限于飞书 Wiki 开放 API 在新建节点时不支持直接指定侧边栏原生 Emoji 图标（Icon）的物理限制，建档时须统一在页面的主标题（`<title>`）前缀硬编码加入匹配的 Emoji 标签作为内页视觉弥补。若要追求侧边栏极致的 Premium 体验，在建档脚本运行后，建议维护人员在飞书客户端内手动为二级分类目录节点（L1b）更换对应 Emoji（仅 8 个大类节点需要手工更换，普通叶子章节可继承默认样式），能瞬间提升知识库格调。

### §7.6 白板（Mermaid 脑图）防丢重绘铁律
* **覆盖写入前剥离属性**：任何 `overwrite` 提交前必须彻底剥离 `<whiteboard>` 上的 `id` 和 `token`（只留 `<whiteboard type="mermaid">`），强制云端重分配 ID。
* **覆盖写入后二次渲染**：`overwrite` 成功后，从响应 `new_blocks` 中按序抓取 `block_type == "whiteboard"` 的新 `block_token`，紧接调用 `whiteboard +update --whiteboard-token <token> --input_format mermaid --source - --overwrite` 将 Mermaid 源码经 stdin 渲染写入。未执行此步 → 网页端画板空白。
* 此两段逻辑分别在 `feishu_wiki/whiteboards.py` 与 `feishu_wiki/writer.py` **唯一实现**，全工具共用，杜绝重复实现导致的遗漏。
* **Mermaid 字符净化**：节点文本内英文冒号 `:` 与英文括号 `()` 须转全角（或文本加引号），避免破坏解析；禁止 `->`/`=>`/`➡️` 等箭头及 `💡` 等 Emoji 混入节点文本。
* **着色语义**：🔴 风险/死穴、🔵 核心系统/根节点、🟢 安全/实践/产出、🟡 过渡/核心观点。

### §7.7 命名与序号规范
* 全局连贯序号前缀 `0X`/`XX`（如 `00. 前言`），保持 Wiki 侧边栏物理顺序。
* 剥离原书自带章节号（如 `1.`）避免「2 个 03」冗余；无自带号的篇章（前言/尾记）也强制编入全局序号。
* **有序列表与子导航前缀数字去重铁律**：在拼装有序列表 `<ol><li>`、模块主标题文字、或在 `<sub-page-list>` 子页面列表中，**必须使用正则表达式（如匹配 `r'^\d+[\.\、\s]+'`）彻底过滤剔除内容自带的硬编码数字序号前缀**！在金句/观点解读提取阶段，**必须主动跳过所有以 `#` 开头的 Markdown 标题行**，并彻底清洗掉金句首尾可能残存的类似 `2.` 或 `1.` 序号前缀，以彻底防范飞书前端渲染出诸如 `1. 1. 标题` 或 `1. 2.` 的重复序号难看问题。

### §7.8 物理合并、降级与金句清洗铁律
* **合并文档标题强制降级铁律**：当多篇正课物理合并为一个周度聚合（L2）大页面时，**每一篇子课在正文中的标题 `<h2>` 必须强制降级为 `<h3>`（或更低）进行呈现**！这是为了保证该聚合页面上层以统一的大 `<h2>` 段落（如“一、本篇金句”、“二、逻辑图示”......“六、完整原文”）统领全局的层级一致性，严禁产生标题层级越级或断裂冲突。
* **首行主标题防重影自动剔除铁律**：当物理拼装子课原文至大聚合页面时，由于大聚合页已用独立的 `<h3>第 N 讲：子课标题</h3>` 标明了边界，**必须使用正则或首行扫描逻辑彻底剔除子课 Markdown 文档首行可能重复出现的主标题（即 `# 子课标题` 或 `## 子课标题`）**！严禁在聚合页面上出现紧邻的两个相同大字标题重影。
* **图片无意义 alt 净化与 caption 紧随段落去重铁律**：在解析 Markdown 图片 `![alt](url)` 时，若 `alt` 内容为无意义的文件路径或资源序列名（如包含 `page00`、`img`、`cover`、`assets` 等字眼），**必须将 caption 属性置空，不生成下方说明**；同时，若原 Markdown 中在图片下一行硬编码写了与 `alt` 内容相同的说明文字（如 `图 1：复利曲线`），**必须对段落正文和 caption 属性进行去重合并**，只保留原生 caption 属性，并将正文中重复的下一行图注段落从 XML 中剔除，防止在页面上出现图注文字上下重复出现两次的现象。
* **金句与核心观点提取净化铁律**：从本地 Markdown 原文抓取“今日概要”或“划重点”段落生成本周核心金句与观点时，**必须用正则表达式对文本进行深度清洗**。彻底剔除如 `## 划重点`、`## 今日概要：`、前导的数字标号以及空行噪声，保证高亮卡片中只呈现纯粹的金句和干货原文。

### §7.9 交互式原文折叠与学术型观点解读分级铁律
* **多课物理合并折叠铁律**：当多篇正课合并拼装到单一大周度聚合页面时，为了杜绝长篇大论带来的视觉闷感与严重的阅读疲劳，**必须将每一篇原文正文，各自封装进 HTML5 原生的 `<details>` 与 `<summary>` 折叠标签中进行展现**。
  - 折叠栏标题必须采用统一格式：`<summary><b>📖 第 N 讲：{讲名}</b></summary>`。
  - 原文全部包裹于 details 中，默认保持折叠。这能让页面折叠时长度缩短 90% 以上，带来极具弹性的交互体验。
* **核心金句与核心观点解读的智识分级去重铁律**：为了杜绝页面内容换汤不换药的机械性重复，金句与观点解读必须在智识层级上实现本质的分层设计：
  - **一、 本篇金句 💡**：只精选摘录原著中极具视觉震撼的一两句“原话名言警句”（通常为 1-2 句），并在正文中使用 `<b><span text-color="rgb(216,57,49)">...</span></b>` 进行加粗红色高亮呈现。
  - **三、 核心观点解读 💡**：必须由 AI 深度提炼和剖析原著每一讲的核心底层思想模型。结构上统一采用 **“核心论点”**（AI 提炼的底层命题）与 **“逻辑拆解”**（AI 深入推演其思想背景与现实边界）两个子列表项目进行深度拆解，严禁在此处直接复制粘贴原著金句。

## ⚙️ 技术痛点攻坚 (Technical Bottlenecks)

* **Grid 嵌套致服务端 Panic (transport: EOF)**：中英双栏长文**仅用一个** `<grid>` + 两 `<column width-ratio="0.5">`，扁平结构解析快、不丢包。
* **异步删除/创建导致重名草稿堆积**：建档走「预扫描复用同名节点」而非「删后建」；万一路径涉及删建，必须 `time.sleep(5)` 等待云端刷新（见元规范一）。
* **OCR 脏数据**：物理过滤 `●`/`■` 等脏序号、重整空行、中英标点统一（§7.4）、智能段落重组（行尾非结束标点则合并，句尾结束标点才断行）。
* **超长文献分页**：正文 >3 万字或 >200 块时按章节物理分割为 `Part N` 并注入前后导航锚点卡（属于生成侧职责，脚本当前未自动分页）。

## 🧠 批判性审视规范 (Critical Thinking Audit)

文献解读须标注逻辑漏洞（置于独立 `<callout>` 警示卡，红/黄底 + `⚠️`/`💡`）：前提假设虚构、因果倒置、幸存者偏差、非黑即白、滑坡谬误、结论边界缺失。按「原文断言 vs 逻辑漏洞/现实边界」对照排版。

## 🔰 端到端工作流（0→1 适用场景）

**典型场景**：把用户拥有或已获授权的一批本地 Markdown 文档（位于私有项目 `source/chapters/*.md`）交给 AI 解读，再批量创建进用户授权的飞书知识库并统一排版。整条链路分三阶段：

> **阶段一 · AI 解读（由 AI 助手执行，产出数据文件）**
> - 读取 `source/chapters/*.md`，按 §页面结构模板生成每篇的结构化内容。
> - 产出 `config/outline.json`：仅含 `chapter_id` / `index` / `title` / `kind` / `parent_chapter_id` / `source_path`。
> - 产出 `generated/mermaid_maps.json`：键为 `chapter_id`，值为 Mermaid 源码。
> - `state/remote_nodes.json` 由脚本回写云端标识；AI 不得把 Token 填入大纲。

> **阶段二 · 建档（脚本）**：`create-nodes` 按大纲批量建子页面并回写 Token（幂等去重）；`update-nav` 在父页面挂载原生 `<sub-page-list>` 导航。（若正文已通过脚本 `overwrite_and_render` 先行灌入，则 `create-nodes` 仅做已存在节点复用。）

> **阶段三 · 打磨（脚本）**：`polish` 落实排版铁律（红字标粗 / Emoji 规范 / 全角净化 / H1 剔除 / 白板防丢重绘）；`restore-wb` 仅在该步未覆盖时单独补绘脑图（文章页 / 总纲页的脑图内容本身为强制项，见 §脑图规范）。

`chapter_id` 是大纲、脑图、生成文件与云端状态之间的稳定关联键。标题可修改，不得作唯一主键。

### ⚠️ 大纲树结构与排序铁律
* **总纲排序规范 (Index 0)**：总纲页的 `kind` 为 `overview`，`index` 必须为 `0` 且在列表首位。
* **多层级目录映射 (Multi-level Tree)**：在 `outline.json` 中用 `parent_chapter_id` 表达层级。当前 `create-nodes` 每次只对一个已确认的父节点执行一批创建；多层结构必须按父节点分批且逐批 dry-run，不得宣称为自动递归建档。
* **标准三层拓扑与拆解生命周期 (3-Layer Topology & Lifecycle)**：
  - 全书导入硬性推荐使用 3 层树状结构进行建档（L0 根合集介绍页 ➔ L1a/L1b 总纲与二级模块目录页 ➔ L2 单篇详细解读叶子页），以防止侧边栏臃肿杂乱。
  - **知识库拆解与写入生命周期顺序必须为：① 文档介绍（L0 根页填充与子模块 cite 导航）➔ ② 策略总纲（L1a 总纲页脑图与 Top 推荐卡写入）➔ ③ 主题分类（L1b 二级目录建档与 Nav 原生挂载）➔ ④ 逐一拆解（L2 详细结构化正文与个篇脑图灌入及 Polish 打磨）**。这一流程可绝对保障知识库层级结构的合理性和自适应扩展。


## 🚀 快速上手 (Quick Start)

```bash
export FEISHU_WIKI_WORKSPACE="/secure/path/feishu-wiki-workspace"
# 只创建本地分层骨架；不猜测空间 ID 或父节点
python3 scripts/init_project.py --project default
bash scripts/setup.sh
source "$FEISHU_WIKI_WORKSPACE/.venv/bin/activate"
# 1) 先预览建档计划；用户确认后才执行正式写入
python3 scripts/feishu_wiki.py create-nodes --dry-run
python3 scripts/feishu_wiki.py create-nodes --space <SPACE_ID> --parent <PARENT_TOKEN>
# 2) 挂载父页面导航
python3 scripts/feishu_wiki.py update-nav --space <SPACE_ID> --parent-obj <OBJ> --parent-node <NODE> --dry-run
python3 scripts/feishu_wiki.py update-nav --space <SPACE_ID> --parent-obj <OBJ> --parent-node <NODE>
# 3) 先 dry-run 预览，确认无误再正式打磨
python3 scripts/feishu_wiki.py prepare --dry-run
python3 scripts/feishu_wiki.py polish --dry-run
python3 scripts/feishu_wiki.py polish --workers 3
# 4)（可选）仅补绘丢失的脑图——文章页/总纲页的脑图内容为强制项，见 §脑图规范
python3 scripts/feishu_wiki.py restore-wb --dry-run
```

完成本地初始化后，仍必须请用户确认飞书空间、父节点和写入范围，
再执行任何云端命令。

## ⚠️ 绝对底线 (Hard Constraints)

1. 富文本嵌套铁律（§7.1）。
2. 白板防丢两阶段（§7.6）—— 唯一实现点为 `feishu_wiki/whiteboards.py` 与 `feishu_wiki/writer.py`。
3. 禁用 `sup` 上标（§7.5）。
4. 标点净化安全边界（§7.4）—— 仅含中文文本节点，跳过公式/代码/脑图/URL。
5. HTML5 原生 details/summary 原文折叠铁律（§7.9）。
6. 核心金句与观点解读智识级分级去重铁律（§7.9）。
7. **Stale 引用物理隔离与 User 身份写入铁律**（§7.6）：使用 `overwrite` 覆写整个页面 XML 时，**必须使用正则强制剥离所有以 `dox` 或 `doxcn` 开头的系统随机分配 ID 属性**，且执行命令必须强制附加 **`--as user`** 身份，以彻底杜绝飞书 API 因 Stale references 判定请求非法，从而把整页正文吞噬清空的隐形灾难。

## 🔧 依赖与初始化 (Prerequisites)

| 依赖 | 安装 | 验证 |
|------|------|------|
| Python 3.8+ | `brew install python`（或用 WorkBuddy 托管 3.13） | `python3 --version` |
| **lark-cli**（飞书官方 CLI，本工具所有云端读写的真正执行者） | `brew install lark-cli` | `lark-cli --version` |
| lark-cli 登录授权 | `lark-cli auth login`（浏览器扫码） | `lark-cli auth status` |
| beautifulsoup4 / Pillow | `bash scripts/setup.sh` 自动装 | `$FEISHU_WIKI_WORKSPACE/.venv/bin/python -c "import bs4; import PIL"` |

* 一键体检：`bash scripts/doctor.sh` 逐项检查上述全部依赖与私有运行文件，给出 [PASS]/[FAIL] 与修复命令，**首次使用务必先跑**。
* 初始化：
  ```bash
  bash scripts/setup.sh    # 在私有工作区创建 .venv、安装依赖，并检查 lark-cli 登录态
  source "$FEISHU_WIKI_WORKSPACE/.venv/bin/activate"
  ```
  缺依赖时脚本打印明确安装提示后退出，不抛 `ModuleNotFoundError`。

## 🔒 安全与演进约定

* 所有云端写操作内置幂等（预扫描去重 / 跳过已存在）与指数退避重试；单篇失败不中断整批，结尾汇总失败列表。
* **写入安全约束**：所有文档覆写前必须生成本地 XML 快照；覆写后白板渲染失败时必须尝试回滚。`restore-wb` 对已存在白板只允许局部渲染，不得为了重绘白板而覆写整页。
* **产物绑定约束**：`push` 必须用 `chapter_id` 或精确 XML `<title>` 证明章节 JSON 归属；仅文件序号相同不得进入写入计划。出现任何预检告警时默认整批中止，只能由用户明确确认后使用 `--allow-partial`。
* **创建安全约束**：预扫描现存子节点失败时必须中止，不得将异常视为空目录继续创建；节点创建命令不得自动重试，响应不确定时应重新预扫描并复用已存在节点。
* 本 Skill 的脚本 / 手册 / `mermaid_maps.json` 任何修改，**须先以报告形式提交用户、经确认后再执行**，且执行前备份原文件。**禁止**自动修改版本号、自动重命名、或自动覆盖写回用户目录。
* 版本历史与逐版经验见 git / 备份目录，不在本文档内以追加段落重复记录。
* **非交互式命令行保障**：所有脚本工具（如 `update-nav`）在自动化或 Agentic 多阶段运行时，必须完全提供且首选命令行传参（如 `--space`、`--parent-node`、`--parent-obj` 等），严禁在无人值守阶段依赖交互式标准输入（stdin），防止任务挂起超时。
* **交付终检与巡检规约 (Final Quality Check)**：在书籍的所有章节覆写与排版打磨完成后，操作 Agent **必须强制对云端文档开展一次彻底的终检**。重点检查项目包括：（a）知识库 L0 根节点是否成功覆写为带简介和 cite 大纲的 Landing Page；（b）总纲页底部的“二级分类导航”是否成功渲染出 `<sub-page-list>` 原生子页面大纲，严禁出现导航区空白遗漏；（c）文章页面正文各模块是否正文完整，Mermaid 脑图白板是否全部渲染展示成功，拒绝静默丢失或白板卡片报错。

## 🤝 并发与多 Agent 协作模型

> 本工具是**无状态飞书 API 封装**（底层走 `lark-cli`），不含任何调用大模型 / 智能体的代码。下文「Agent」泛指**操作这些脚本的人或 AI 助手**本身，并非被脚本调用的子智能体。

### 1. 并发的本质：`--workers N` 云端并发
* `polish` 与 `restore-wb` 均支持 `--workers N`（默认 1 串行，建议 ≤5），通过 `ThreadPoolExecutor` 实现**多章节并发**调用飞书 API。
* 这是「飞书 API 调用并发」，不是「多 Agent 编排」。Agent 负责**编排驱动**这些子命令；子命令本身不反向调用 Agent。

### 2. 安全的并发边界（务必遵守）
* ✅ **不同文档 / 不同 Agent 可并发**：`create-nodes` 的「预扫描复用同名节点」幂等 + `polish`/`restore-wb` 的「单篇失败不中断整批」保证多章节、多 Agent 同时跑也安全。
* ❌ **同一文档禁止多 Agent 并发 `overwrite`**：`overwrite` + 白板二次 `render` 不是原子操作，竞态会导致（a）白板渲染空白、（b）内容相互覆盖错乱。多 Agent 协作时，请按「一文档一写入者」分工（例如按章节区间拆分，或串行跑同一文档）。
* ⚠️ 即便多文档并发，也建议 `--workers` 不超过 5，避免触发飞书频控（`run_cmd` 已内置指数退避重试兜底）。

### 3. 多 Agent 协作推荐姿势
* 每个 Agent 认领**不同 `chapter_id` 集合**，分别调用 `polish --workers N`；共享大纲、脑图和远端状态时必须只读，由单一写入者回写状态。
* 父页面导航 `update-nav` 与总纲页重绘由单一 Agent 串行收口，避免并发写同一父节点。
