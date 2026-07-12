# AI 与开发者工作规范

本文件是开发仓库的操作约束。任何 AI 或开发者在修改项目前都必须先阅读本文件和 `docs/PROJECT_STRUCTURE.md`。

## 单一代码源

- 正式业务代码只能放在 `skill/feishu-wiki-importer-optimizer/scripts/`。
- 根目录同名 Python/Shell 文件在迁移期只能是薄兼容入口，不得增加业务逻辑。
- 修复 Bug 时先改正式实现，再运行测试；不得只修根目录兼容文件。
- ZIP、缓存、快照、备份、预览、日志和生成内容都不是源代码，禁止直接修改后当作代码提交。

## 运行数据与发布边界

- 仓库只保存代码、合成示例、测试和开发文档。
- 原文、图片、真实飞书资源标识、空间标识、本机绝对路径、评论、快照与中间产物只能存在仓库外的私有工作区。
- 新任务未指定项目时，默认使用 `<workspace>/projects/default/`；不得把运行文件放回仓库根目录。
- 只能通过 `python3 tools/build_release.py` 生成发布包。不得直接压缩仓库、Skill 目录或私有工作区。
- Skill 发布包只能包含白名单中的 `SKILL.md`、`agents/`、`scripts/`、`references/` 和 `assets/`。

## 配置与项目选择

工作区选择优先级固定为：

1. 命令行 `--workspace` / `--project`。
2. 环境变量 `FEISHU_WIKI_WORKSPACE`。
3. `workspace.json` 中的 `default_project`。
4. `projects/default/`。

本地项目骨架可以自动建立；云端 `space_id`、父节点和写入范围不得猜测，缺失时必须询问用户。

## 修改与验证

- 修改前确认存在可恢复备份；涉及运行数据时必须先复制、校验，不得直接移动或覆盖。
- 云端写操作必须先 dry-run；未获得用户确认时不得对真实飞书资源写入。
- 每批修改后至少运行离线测试、Skill 校验、发布扫描、`git diff --check` 和 `git fsck --full`。
- 修改配置格式时必须保留旧格式的读取或明确的迁移器，直到迁移验证完成。
