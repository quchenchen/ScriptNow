# 12 · 剧本纸样式渲染 + .docx 导出

- **Status**: done (backend + export button; ScriptSheet.vue 版式 defer Batch 3)
- **Type**: feature
- **Blocked by**: 06
- **Blocks**: —
- **Est**: M
- **Parent PRD**: docs/PRD-V5.md §User Stories #39, #40, #41, #42, #44

## What to build

### 后端 (done)

- **Format checker** (`app/services/format_checker.py`)：
  - 检查 markdown 残留（`**bold**` / `` `code` `` / ``` fence / `# heading` / `- bullet`）
  - 场景标题格式（缺 `【场景N】` / 场景标题空 → issue）
  - 对白全角冒号（半角 `:` → medium）
  - 占位符残留（`对白：` / `旁白：` 空行）
  - 连续空行 > 3
  - Score 100 起始，high/medium/low → -15/-10/-5
- **docx 导出** (`app/services/docx_exporter.py`)：
  - `render_project(project, episodes)` → bytes
  - Cover page + episode heading + 场景标题加粗 + 动作行斜体缩进 + 对白粗体角色名
  - 用 python-docx（issue #01 已 pin `python-docx==1.1.2`）
- **API** `POST /api/projects/{pid}/export?format=docx` → attachment download
- **Ralph loop 集成**：`ralph_service.run_iteration` 除了 AI-tell detector 也跑 format_checker，issues 合并进 review issues，format score < 70 拉低总分 `(70-score)*0.3`

### 前端 (done)

- `useWorkspace.ts::exportAll` 改成走后端 API：`POST /api/projects/{pid}/export?format=docx`, `responseType: blob` → download .docx
- 用 `Content-Disposition` 里的 filename（后端根据 project.title 生成）

### 前端 UI 精修 (deferred to Batch 3)

- `ScriptSheet.vue` 视觉版式（【场景N】加粗独立行 + △ 楷体缩进 + 对白右缩进对齐）
- `SceneEditor.vue` 单场景就地编辑（textarea 保存 + 格式辅助按钮）
- Inline reprompt（选中一段 → 局部改写）
- Scene 版本历史

## Acceptance criteria

- [x] 一键 `.docx` 导出可下载，Word 打开：cover + 每集独立标题 + 场景标题加粗 + 动作行 △ + 对白角色名加粗（`test_export_returns_docx_with_scenes` 覆盖）
- [x] format_checker 检出 markdown 残留、缺场景头、半角冒号、占位符残留、过多空行（11 tests 覆盖）
- [x] Writing Agent 完成一集后跑 format_checker，issues 反哺回 Ralph Loop（`ralph_service` 集成，与 detector 并列写入 review_issues）
- [x] Owner isolation（Bob 无法导出 Alice 项目 → 404）
- [x] 不支持的 format 返回 400
- [x] 空项目也能导出（Cover only）
- [ ] Episode 详情按剧本纸格式渲染 — Batch 3（现在 `<pre>` 显示够用）
- [ ] Inline reprompt — Batch 3
- [ ] `.fdx` (Final Draft) 导出 — P1，不在本 slice 范围
- [ ] Scene 版本历史 — YAGNI 暂不做

## Notes

- python-docx 已在 issue #01 pin，无新增依赖
- Format checker 是纯函数，pytest 0.07s 跑完 11 test
- Ralph loop 集成后，一个漂亮但格式脏的一集会自然掉到 revise 段
- ScriptSheet.vue 视觉版式属于 UI 精修，跟 CharacterPanel/ForeshadowBoard 等一起 Batch 3 组件库升级时统一做
