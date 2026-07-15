# AGENTS.md — ScriptFlow 项目 Agent 协作约定

_任何 AI Agent（Kiro / Claude Code / Cursor / QwenPaw agent）在这个仓库里干活前，先读这份。_

## 项目一句话

**ScriptFlow**：让好剧本"长出来"的 AI Agent 团队协作平台。

- 产品定位：AI Agent 团队自主推进，用户是总指挥
- 核心隐喻：**Growing**（生长）而非 **Assembling**（拼凑）—— 见 [ADR-0001](./docs/adr/0001-adopt-growing-metaphor.md)
- 主线文档：[`CONTEXT.md`](./CONTEXT.md)（领域语言）+ [`docs/PRD-V5.md`](./docs/PRD-V5.md)（主线 PRD，Phase 1 产出）+ [`docs/adr/`](./docs/adr/)（决策历史）
- 历史文档：[`docs/archive/`](./docs/archive/)（PRD-V3 / SPEC-V4 / PLAN 等，作为参考保留，不再是主线）

## 技术栈

- **Backend**: FastAPI + AgentScope 2.0 + DashScope LLM + SQLite (aiosqlite)
- **Frontend**: Vue 3 + Vite + TypeScript
- **Package management**: 尚未规范化 —— 建立 `pyproject.toml` 是 Phase 3 早期任务

## 读代码前先读

1. **[`CONTEXT.md`](./CONTEXT.md)** — 项目的 ubiquitous language。所有命名以这里为准。
2. **[`docs/adr/`](./docs/adr/)** — 已定的架构决策。改代码前先看有没有相关 ADR，改动违背 ADR 时要么绕开、要么写新 ADR 覆盖旧的。
3. **[`docs/PRD-V5.md`](./docs/PRD-V5.md)** — 当前主线 PRD。

## Agent skills

本项目使用 [Matt Pocock's Skills for Real Engineers](https://github.com/mattpocock/skills)。执行 agent（QwenPaw 上的阿泡）在自己的 workspace 里维护 skill 定义，本仓库只承担 skill 的产物：CONTEXT / PRD / ADR / issues。

### Issue tracker

本地 markdown。issue 文件住在 `.scratch/scriptflow-v5/NN-slug.md`。详见 [`docs/agents/issue-tracker.md`](./docs/agents/issue-tracker.md)。

### Triage labels

用默认的 5 个标签：`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`。详见 [`docs/agents/triage-labels.md`](./docs/agents/triage-labels.md)。

### Domain docs

Single-context：一份 [`CONTEXT.md`](./CONTEXT.md) + [`docs/adr/`](./docs/adr/) 在仓库根。详见 [`docs/agents/domain.md`](./docs/agents/domain.md)。

## 代码约定

### 命名

- Python：`snake_case` 函数 / 变量，`PascalCase` 类，`SCREAMING_SNAKE` 常量
- TypeScript：`camelCase` 函数 / 变量，`PascalCase` 类型 / 组件
- **术语一律用 [CONTEXT.md](./CONTEXT.md) 里的词汇** —— 别写 `role` / `persona` 请写 `character`；别写 `pipeline` / `workflow` 请写 `growth_tree`

### 目录

```
agent-script-platform/
├── AGENTS.md              # 你现在看的这份
├── CONTEXT.md             # 领域语言
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routers
│   │   ├── core/          # 领域核心（LLM gateway、agent orchestra、context engine）
│   │   ├── agents/        # Agent 定义（Ideation / Structure / Writing / Review / ...）
│   │   ├── skills/        # Agent 使用的领域 prompt 模板（.md 文件）
│   │   ├── models/        # ORM 模型（Phase 3 早期收敛，目前 models.py 和 main.py 里的 CREATE TABLE 并存 —— 见 issue #001）
│   │   └── main.py
│   └── data/              # SQLite 存储 —— *.db 已被 .gitignore
├── frontend/
│   └── src/
│       ├── pages/         # Workspace / Dashboard / Login
│       ├── components/    # 可复用 UI 组件
│       └── composables/   # Vue composition API 抽象
├── docs/
│   ├── PRD-V5.md          # 主线 PRD
│   ├── adr/               # 架构决策记录
│   ├── agents/            # Agent 协作配置（issue tracker 等）
│   └── archive/           # 历史文档
├── .scratch/
│   └── scriptflow-v5/     # 本地 markdown issue tracker
└── design/                # UI 设计稿 HTML（探索性）
```

### 测试

- 后端：`pytest` + `pytest-asyncio`。测试文件 `backend/tests/test_*.py`。
- 前端：`vitest` + `@vue/test-utils`。测试文件与源文件同目录 `*.spec.ts`。
- **测试策略**：只测 public interface，不测 implementation detail。参考 [`skills/engineering/tdd/SKILL.md`](https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/SKILL.md)（在阿泡的 agent workspace 里）。

### Commit 规范

- 中文 commit message 可以，短句
- 每个 commit 对应一个 slice 的一步（or 一个 tracer bullet 里的 red/green/refactor 一步）
- 不要 amend 已 push 的 commit
- 不要 force push 到 main

### 敏感信息

- `.env.*` 已被 `.gitignore`
- 从不把 `DASHSCOPE_API_KEY` / `OPENAI_API_KEY` / `JWT_SECRET` 提交到 git
- 生产 secrets 走环境变量或未来的密钥管理

## 怎么跑（开发时）

**目前无 README，缺 `pyproject.toml` 和 requirements 锁定** —— 这是 Phase 3 早期 issue #002 会补上。以下是当前手动步骤：

```bash
# 后端
cd backend
source .venv/bin/activate    # .venv 已存在
export DASHSCOPE_API_KEY=...
export JWT_SECRET=...        # 生产必需，开发可省
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev
```

## 阿泡的执行约定

- **一次一个问题** —— 但用户明确授权"自动化开发"后，我按 plan 推进，只在关键节点 checkpoint
- **文件级操作可回滚 → 不问；删代码 / 破坏性 schema 变更 / git push / 跨模块重写 → 问**
- 每个 Phase 结束会 checkpoint 告知进度和产出，等用户 ack 或直接放行进下一 Phase
- **保留旧版本作为参考**（rename to `foo_v1.py` 或归档到 `docs/archive/`），不轻易 `rm`

## 相关链接

- 阿泡（agent）的 skill 索引：`~/.copaw/workspaces/Real-Engineers/skills/INDEX.md`
- 上游 Matt Pocock skills：https://github.com/mattpocock/skills
