# 旧扁平私有运行数据（兼容期）

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

可将 `assets/*.example.json` 复制到该工作区作为起点，但示例不能用于真实写入。
真实 `node_token`、`obj_token`、空间标识和课程/书籍内容均属于私有运行数据。

当前 CLI 仍以本布局的 `mappings/chapters_nodes.json` 为默认输入。不要将新布局的
`config/outline.json` 直接传给旧 `--mapping`；它们的 Schema 不同。
