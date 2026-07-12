# 飞书知识库导入与排版工具

将本地文档的结构化解读结果写入飞书 Wiki，并完成建档、导航、富文本排版和 Mermaid 白板重绘。

本仓库是**开发仓库**；唯一可发布的 Skill 位于
[`skill/feishu-wiki-importer-optimizer/`](skill/feishu-wiki-importer-optimizer/)。

## 安全边界

- 不要将原书、课程原文、图片、评论、真实飞书映射、快照或验证脚本提交到本仓库。
- 不要从仓库根目录直接压缩或上传。发布只允许运行 `python3 tools/build_release.py`。
- `node_token`、`obj_token`、空间标识和本机绝对路径均按私有运行数据处理。
- `.gitignore` 只降低 Git 误提交概率，不能保护 Finder 压缩、目录复制或第三方打包器；发布白名单才是安全边界。

## 目录

```text
.
├── skill/feishu-wiki-importer-optimizer/  # 唯一可发布包
│   ├── SKILL.md
│   ├── agents/
│   ├── scripts/
│   ├── references/
│   └── assets/                            # 仅合成示例
├── tests/                                 # 开发期离线测试
├── tools/                                 # allowlist 打包与扫描
├── docs/                                  # 开发/发布说明
└── <repo>.private-workspace/              # 仓库外私有数据（不发布）
```

真实运行数据的目录约定见
[`project-layout.md`](skill/feishu-wiki-importer-optimizer/references/project-layout.md)。
开发者和 AI 修改前还必须阅读 [`AGENTS.md`](AGENTS.md) 与
[`PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md)。

新工作区可先离线初始化：

```bash
python3 skill/feishu-wiki-importer-optimizer/scripts/init_project.py \
  --workspace /secure/path/feishu-wiki-workspace \
  --project default
```

初始化器不访问飞书，也不猜测空间或父节点。当前旧 CLI 仍读取
`mappings/chapters_nodes.json`；新 `config/outline.json` 暂不能直接传给 `--mapping`。

## 兼容旧命令

根目录的 `feishu_doc_tools.py`、`feishu_prepare_chapters.py`、
`feishu_push_chapters.py`、`setup.sh` 和 `doctor.sh` 是兼容入口，仍可使用；实现已迁移到 Skill 的 `scripts/`。

```bash
# 安装私有运行环境；默认使用同级 <repo>.private-workspace/
bash setup.sh

# 明确选择私有运行目录（建议）
export FEISHU_WIKI_WORKSPACE="/secure/path/feishu-wiki-workspace"

# 原有命令保持可用
python3 feishu_doc_tools.py create-nodes --space <SPACE_ID> --parent <PARENT_NODE>
python3 feishu_doc_tools.py polish --dry-run
```

请先将真实 `chapters_nodes.json` 和 `mermaid_maps.json` 放入私有工作区的 `mappings/`；也可通过 `--mapping` 和 `--maps` 显式指定私有路径。

## 开发与发布检查

```bash
# 离线回归测试（不会访问飞书）
python3 -m unittest discover -s tests -v

# 仅检查发布清单
python3 tools/check_release.py

# 生成唯一允许上传的 ZIP
python3 tools/build_release.py
```

产物会写入被 Git 忽略的 `outputs/`。上传前仍应检查 ZIP 清单并确认所有示例数据均为合成数据。

## 许可证与第三方内容

本仓库内的代码以 [MIT License](LICENSE) 发布。MIT 仅覆盖本仓库代码，不覆盖任何书籍、课程、图片、评论、云端文档或其他第三方内容；除非已取得明确再分发许可，这些材料不得加入仓库或发布包。

## 公开历史处置

此前公开 Git 历史曾包含真实资源标识和路径。目录重构只能防止再次泄露，**不能删除已公开的 Git blob**。在重新公开发布前，应完成飞书权限复核、Git 历史重写或新建干净仓库，并按泄露事件处理已有 clone、缓存和镜像。
