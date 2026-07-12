# 私有项目布局

当任务需要创建、定位或迁移本地项目时，使用本规范。

## 选择项目

按以下顺序选择：

1. 用户通过 `--workspace` / `--project` 指定的项目。
2. `FEISHU_WIKI_WORKSPACE` 指定的工作区。
3. `workspace.json` 中的 `default_project`。
4. `projects/default/`。

本地项目不存在时，可运行：

```bash
python3 scripts/init_project.py --workspace <workspace> --project default
```

不要猜测云端空间 ID、父节点或写入目标；缺失时询问用户。

## 固定目录

```text
<workspace>/
├── workspace.json
├── projects/<slug>/
│   ├── project.json
│   ├── source/chapters/
│   ├── source/images/
│   ├── config/outline.json
│   ├── generated/prepared/
│   ├── generated/mermaid_maps.json
│   ├── state/remote_nodes.json
│   ├── state/uploaded_images.json
│   ├── previews/
│   ├── backups/
│   ├── cache/
│   └── logs/
└── archives/
```

- `outline.json` 只保存章节结构与相对路径。
- `remote_nodes.json` 只保存云端节点状态。
- 使用稳定 `chapter_id` 关联大纲、Mermaid 和云端状态；不以可变的标题作唯一键。
- 目录权限应为 `0700`，配置和状态 JSON 应为 `0600`。
- 上述整个工作区都是私有运行数据，不得进入 Git 或 Skill 发布包。

字段规则见 `references/*.schema.json`。
