# 09 · Ralph Loop 复活（Evolution Tier 1）

- **Status**: done (backend complete + manual trigger endpoint; auto-hook + UI deferred to Batch 3)
- **Type**: feature
- **Blocked by**: 05, 07
- **Blocks**: — (Reflection / Style Library 各自 slice)
- **Est**: L
- **Parent PRD**: docs/PRD-V5.md §User Stories #26-#29; ADR-0003

## What to build

单集内 写 → 审 → 打分 → 修 → 再审 循环。

**后端 (done)：**
- `app/services/evolution_engine.py` — 纯函数 `ralph_decide(review_score, pass_threshold, revise_threshold, retry_count, max_retries) → Decision`（pass / revise / restructure / escalate）
- Review Agent (`app/services/review_agent.py`) —
  - 载入 `app/skills/review/main.md` 作 system prompt
  - `_call_review_llm` (可 monkeypatch 供 test) 调 `_build_model(model_id)`
  - `_parse_review_json` 抽 fenced/bare JSON，抗噪声（garbage input → overall_score=0）
- `app/services/ralph_service.py` — 组合 engine + agent + DB
  - `run_iteration(project_id, episode_id, model_id)` — 加载阈值、组装 episode text (from scenes 表)、调 review、决策、写 `ralph_iterations`、更新 episode.status
  - `list_iterations(episode_id)` — 历史
- 新表 `ralph_iterations` (Alembic 0005) — `id / episode_id / iteration / writing_output / review_score / review_dimensions JSON / review_issues JSON / decision / created_at`
- `projects` 表加 3 字段：`ralph_pass_threshold` (85) / `ralph_revise_threshold` (60) / `ralph_max_retries` (3)
- API `app/api/ralph.py`：
  - `GET /api/projects/{pid}/episodes/{ep_num}/ralph` — 一集完整历史
  - `POST /api/projects/{pid}/episodes/{ep_num}/ralph` — 手动触发一轮，body 可选 `{"model": "..."}`
- 决策生效：`Decision.PASS` → episode.status=`done`，`Decision.ESCALATE` → `human_review_needed`

**前端 (deferred to Batch 3)：**
- `RalphLoopView.vue` 可视化 — Batch 3 UI 库升级时统一做
- Workspace 主视图 —— 当前正在写的 Episode 上方显示活的 Ralph loop
- Project settings 面板可调阈值 — 后端 API 已支持通过 project 字段更新

## Acceptance criteria

- [x] `pytest test_ralph_loop.py`：17/17（engine 边界 6 + service persistence & escalate 3 + API history & trigger & isolation 4 + empty-episode 1 + parser 4）
- [x] 阈值可 project 级配置 + 生效（`_load_project_thresholds` 从 DB 读，缺省 fallback）
- [x] 三次未通过 → 状态转 `human_review_needed`（test_service_escalates_after_max_retries 覆盖：4 轮拿到 [revise, revise, revise, escalate]）
- [x] 一集写完 → 手动调 POST /ralph → 自动跑 Review → 决策入库
- [ ] **自动触发**：Writing Agent 写完一集自动 chain 到 Review — 留 Batch 3 (需和 workspace agent chat SSE 流集成，前端也需要显示循环过程)
- [ ] 前端过程感可视化 — Batch 3

## Notes

- Review JSON schema 通过 prompt 约束（temp 未强制，AgentScope default）；`_parse_review_json` 兼容 fenced/bare/garbage 三态
- 六维在 prompt 里定义（商业性25% / 叙事性30% / 人物20% / 技术15% / 创新10%），`summarize_dimensions` 助 UI 短标签
- `_call_review_llm` 是 monkeypatch 点 — tests 全部 stub 掉，从不打 LLM，跑 15s
- **手动触发** 已够作为 tracer bullet：用户在 UI 点"重审"按钮就能走完整循环；自动 hook 属于流程改造，独立 slice 做
- 循环里每次生成的 SSE 推送 — 也是 Batch 3 UI slice 的核心工作
