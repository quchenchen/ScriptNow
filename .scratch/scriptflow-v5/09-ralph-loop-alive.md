# 09 · Ralph Loop 复活（Evolution Tier 1）

- **Status**: proposed
- **Type**: feature
- **Blocked by**: 05, 07
- **Blocks**: — （长尾 Reflection / Style Library 各自 slice）
- **Est**: L
- **Parent PRD**: docs/PRD-V5.md §User Stories #26-#29; ADR-0003

## What to build

单集内 写 → 审 → 打分 → 修 → 再审 循环。当前是死代码，现在**从零重写**（放弃旧 review_agent.py，但复用它的 prompt 六维思路）。

**后端：**
- 新建 `backend/app/services/evolution_engine.py`
  - 纯函数：`ralph_decide(review_score, revise_threshold, pass_threshold, retry_count, max_retries) -> Decision` (`pass` / `revise` / `restructure` / `escalate`)
  - 单测覆盖所有阈值边界
- 新建 `Review` Agent（用 AgentScope，接 `backend/app/skills/review/main.md` 的六维 prompt）
- 新建 `/api/projects/{pid}/episodes/{ep}/ralph` 端点：
  - GET → 一集的 Ralph loop 历史（`ralph_iterations` 表）
  - POST → 手动触发新一轮
- Writing Agent 完成一集 → 自动触发 Review → 循环调度到通过或 escalate
- 数据：`ralph_iterations` 表（`episode_id`, `iteration`, `writing_output`, `review_score`, `review_dimensions` JSON, `review_issues` JSON, `decision`, `created_at`）
- 配置：project 级 `ralph_pass_threshold` (默认 85), `ralph_revise_threshold` (60), `ralph_max_retries` (3)

**前端：**
- `RalphLoopView.vue`：可视化组件
  - 一列纵向流程：`#1 · 72分（人物不足 2 项，节奏偏慢）→ 修改中` → `#2 · 84分 → 通过 ✅`
  - 每轮可展开看 diff / issues 详情
- Workspace 主视图 —— 当前正在写的 Episode 上方显示活的 Ralph loop
- Project settings 面板可调阈值

## Acceptance criteria

- [ ] 一集写完 → 自动跑 Review → 若 <85 触发 Revise → 循环可视化在 UI 上明确可见
- [ ] 三次未通过 → 状态转 `human_review_needed`，UI 显示提示
- [ ] 阈值可 project 级配置 + 生效
- [ ] `pytest test_evolution_engine.py` 覆盖阈值决策纯函数
- [ ] `pytest test_ralph_integration.py` 覆盖端到端一集完整循环（fixture LLM response）

## Notes

- Review 打分用 JSON schema 强约束（temperature=0.3、response_format json_object）
- 六维：人物 / 情节 / 对白 / 节奏 / 钩子 / 类型契合度；每维 0-100，overall = 加权平均（权重可 config）
- 循环里的每次生成都要 SSE 推给前端，让"过程感"可见
- **这是 Q老师说的过程感的核心触点** —— UI 要下功夫
