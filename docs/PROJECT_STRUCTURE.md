# 项目结构与文件归属规范

## 1. 三个物理边界

### 开发仓库

仅保存可公开、可审查、可重建的内容：

```text
<repo>/
├── AGENTS.md                         # AI/开发者操作约束
├── README.md
├── skill/feishu-wiki-importer-optimizer/ # 唯一可发布 Skill
├── tests/                            # 离线测试
├── tools/                            # 发布、审计工具
└── docs/                             # 开发文档，不进入 Skill 包
```

`skill/feishu-wiki-importer-optimizer/scripts/` 是业务代码的单一权威位置。
根目录的同名文件仅为迁移期兼容入口。当前已完成「测试切换到正式代码」
和「输出弃用提示」；待私有工作区迁移验证后删除根目录兼容入口。

### Skill 发布包

只包含执行任务必需的内容：

```text
feishu-wiki-importer-optimizer/
├── SKILL.md
├── agents/
├── scripts/
├── references/
└── assets/          # 仅机器 Schema 和合成示例
```

发布是 allowlist 模型。新增 Skill 文件时，必须同步更新 `tools/build_release.py` 和发布包测试。

### 私有工作区

所有输入、运行状态和过程产物都放在仓库外：

```text
<workspace>/
├── workspace.json
├── projects/
│   └── <project-slug>/
│       ├── project.json
│       ├── source/
│       │   ├── chapters/       # 用户授权的原始文档
│       │   └── images/         # 用户授权的原始图片
│       ├── config/
│       │   └── outline.json    # 章节结构，不放云端 Token
│       ├── generated/
│       │   ├── prepared/       # 可重建的中间结果
│       │   └── mermaid_maps.json
│       ├── state/
│       │   ├── remote_nodes.json
│       │   └── uploaded_images.json
│       ├── previews/
│       ├── backups/
│       ├── cache/
│       └── logs/
└── archives/                         # 工作区级历史归档
```

默认权限为目录 `0700`、配置和状态文件 `0600`。

## 2. 数据职责分离

| 文件 | 职责 | 可否公开 |
|---|---|---|
| `workspace.json` | 工作区版本和默认项目 | 否（运行环境配置） |
| `project.json` | 项目名称、路径和状态 | 否 |
| `config/outline.json` | 章节 ID、层级、标题和源文件相对路径 | 否 |
| `state/remote_nodes.json` | 章节 ID 与飞书 `node_token`/`obj_token` 的关联 | 否，敏感状态 |
| `generated/mermaid_maps.json` | 以章节 ID 为键的 Mermaid 源码 | 否，派生内容 |
| `assets/*.example.json` | 不含真实内容的合成示例 | 是，经扫描后随 Skill 发布 |
| `references/*.schema.json` | 机器可读配置规则 | 是 |

`chapter_id` 是本地结构、云端状态和生成产物之间的稳定关联键。标题可以修改，不得再以标题作为唯一主键。

## 3. 配置选择优先级

1. CLI 显式传入的 `--workspace` 和 `--project`。
2. `FEISHU_WIKI_WORKSPACE` 指定的工作区。
3. `<workspace>/workspace.json` 的 `default_project`。
4. `<workspace>/projects/default/`。

自动选择只适用于本地目录。云端空间、父节点、目标文档和正式写入仍必须由用户显式确认。

## 4. 命名与生命周期

- 项目 slug 仅使用小写字母、数字和连字符，例如 `finance-course`。
- 章节使用稳定 `chapter_id`，例如 `chapter-001`；文件名可另行包含排序和中文标题。
- `source/` 是受控输入，不得被清理脚本删除。
- `generated/`、`previews/`、`cache/` 是可重建产物。
- `state/` 是外部系统状态，写入前备份，只能原子替换。
- `backups/` 是项目级恢复点，`archives/` 是不再参与当前执行的历史资料。
- `logs/` 不得记录完整 Token、原文或未脱敏请求体。

## 5. 初始化

新项目使用离线初始化器：

```bash
python3 skill/feishu-wiki-importer-optimizer/scripts/init_project.py \
  --workspace /secure/path/feishu-wiki-workspace \
  --project default
```

已有文件默认不覆盖。`--force` 仅在需要重建配置骨架时使用，初始化器会先将被替换文件备份到 `<workspace>/archives/init-project/<timestamp>/`。
