# 12 · 剧本纸样式渲染 + .docx 导出

- **Status**: proposed
- **Type**: feature
- **Blocked by**: 06
- **Blocks**: —
- **Est**: M
- **Parent PRD**: docs/PRD-V5.md §User Stories #39, #40, #41, #42, #44

## What to build

Craft Standard 落地的第一批：**看着像剧本 + 能导出剧本**。

**前端：**
- `ScriptSheet.vue`：
  - 剧本纸版式：`【场景N】地点·时间` 独立行 + 加粗
  - `△` 首行缩进 + 楷体
  - `角色：对白` 姓名列对齐右缩进 + 宋体
  - 阅读字号 + 行距 + 页面白边
- `SceneEditor.vue`：单场景就地编辑（textarea + 保存），格式辅助（自动加 `△` / `【场景N】` 便利按钮）
- Inline reprompt：选中一段 → 弹出对话框 → 输入"改指令" → 调用 Agent 局部改写
- 每个 Scene 有版本历史（简单版：DB 存旧值 JSON array）

**后端：**
- 新建 `backend/app/api/export.py`：
  - `POST /api/projects/{pid}/export?format=docx` → 返回 .docx 二进制流
- 用 `python-docx` 库按剧本纸格式生成 .docx（标题页 + 场景块 + 角色对白 + 页头页脚）
- **格式校验器**：`backend/app/services/format_checker.py`
  - 输入：Episode / Scene content
  - 输出：list of issues（缺 `【场景】` 头、`△` 不规范、对白格式错、有 markdown 残留等）
- Writing Agent 完成一集后跑 format_checker，issues 反哺回 Ralph Loop（记入 review issues）

## Acceptance criteria

- [ ] Episode 详情按剧本纸格式渲染（`【场景1】` 加粗独立行、`△` 缩进、对白对齐）
- [ ] 单 Scene 就地编辑保存工作
- [ ] Inline reprompt 一段 → Agent 局部改写返回 → 用户可 accept/reject
- [ ] 一键 `.docx` 导出可下载，Word 打开格式正确
- [ ] format_checker 检出 markdown 残留（如 `**加粗**`）、缺场景头等常见问题
- [ ] `backend/tests/test_export_docx.py` 生成 → parse 校验
- [ ] `backend/tests/test_format_checker.py` 覆盖 5+ 常见问题

## Notes

- `.fdx` 导出（Final Draft）放到 P1，本 slice 只做 `.docx`
- 版本历史用极简的 JSON array 存 Scene 里，别搞独立表（YAGNI）
- Inline reprompt 用短会话 Agent，不动主创作 flow
