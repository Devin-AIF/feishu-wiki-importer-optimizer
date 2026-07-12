# 旧扁平私有运行数据（只读兼容与迁移）

> 本布局仅用于兼容现有项目。新项目使用
> [`project-layout.md`](project-layout.md) 中的 `projects/<slug>/` 分层结构。

不要把真实章节、映射、文档快照、图片缓存或验证脚本放入 Skill 目录。

运行脚本前，准备一个私有工作区：

```text
<workspace>/
├── mappings/
│   ├── chapters_nodes.json
│   └── mermaid_maps.json
├── chapters/
├── scratch/
├── runtime_backups/
├── previews/
└── cache/
```

通过环境变量指定位置；未设置时，开发仓库会优先使用同级的
`<repo>.private-workspace`，独立安装则使用用户的本地状态目录。

```bash
export FEISHU_WIKI_WORKSPACE="/secure/path/feishu-wiki-workspace"
```

真实 `node_token`、`obj_token`、空间标识和课程/书籍内容均属于私有运行数据。

正式 CLI 在显式 `--mapping` 时仍能读取旧数组，但默认路径已是新项目的
`config/outline.json` + `state/remote_nodes.json`。不得继续在旧布局中创建新项目。

迁移步骤：

```bash
# 只预检，不写文件
python3 scripts/migrate_workspace.py --workspace <workspace>
# 已校验独立备份后才执行
python3 scripts/migrate_workspace.py --workspace <workspace> --apply
```

迁移器将大纲与云端状态拆分，把 Mermaid 键改为稳定 `chapter_id`，并将
`.local/.bak/.free` 等历史变体连同旧布局归档。任何无法关联的脑图键都会使迁移在切换前中止。
旧 `scratch/chapter_*.json` 只有在 `chapter_id` 或 XML `<title>` 与当前大纲一致时才进入
`generated/prepared/`；无法证明归属的产物仅保留在迁移归档，禁止按数字序号盲推。
