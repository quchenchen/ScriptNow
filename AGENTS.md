# AGENTS.md — ScriptFlow V7 Agent 协作约定

_任何 AI Agent（Kiro / Claude Code / Cursor / QwenPaw agent）在这个仓库里干活前，先读这份。_

## 当前唯一开发基线

**ScriptFlow V7 是全新产品开发。** 开始任务前必须先读：

1. [`docs/v7-spec-v1.1/00-README.md`](./docs/v7-spec-v1.1/00-README.md)
2. [`docs/v7-spec-v1.1/01-PRD-V7.md`](./docs/v7-spec-v1.1/01-PRD-V7.md)
3. [`docs/v7-spec-v1.1/02-LEGACY-DECONTAMINATION.md`](./docs/v7-spec-v1.1/02-LEGACY-DECONTAMINATION.md)

根目录旧 `CONTEXT.md`、`docs/PRD-V5.md`、旧 ADR、V5/V6 产品文档与代码仅作历史研究或待评估资产，**不得作为 V7 需求依据，不得被 V7 新代码直接导入**。复用必须先通过契约对照和 characterization test。

Script 与 Novel 是独立产品领域，只共享 platform 层；禁止共享正文、StoryMap、Writer、审读、格式和导出领域模块。

## 历史项目一句话

**ScriptFlow**：让好剧本"长出来"的 AI Agent 团队协作平台。

- 产品定位：AI Agent 团队自主推进，用户是总指挥
- 核心隐喻：**Growing**（生长）而非 **Assembling**（拼凑）—— 见 [ADR-0001](./docs/adr/0001-adopt-growing-metaphor.md)
- 历史文档：[`CONTEXT.md`](./CONTEXT.md) + [`docs/PRD-V5.md`](./docs/PRD-V5.md) + [`docs/adr/`](./docs/adr/)，仅作 V5 研究材料
- 历史文档：[`docs/archive/`](./docs/archive/)（PRD-V3 / SPEC-V4 / PLAN 等，作为参考保留，不再是主线）

## 技术栈

- **Backend**: FastAPI + AgentScope 2.0 + DashScope LLM + SQLite (aiosqlite)
- **Frontend**: Vue 3 + Vite + TypeScript
- **Package management**: 尚未规范化 —— 建立 `pyproject.toml` 是 Phase 3 早期任务

## 读代码前先读

只读取本文件“当前唯一开发基线”列出的 V7 文档。需要评估复用时，才按 `02-LEGACY-DECONTAMINATION.md` 定向读取旧代码及其测试；不得先读旧 CONTEXT/PRD 再反推 V7 设计。

## Agent skills

本项目使用 [Matt Pocock's Skills for Real Engineers](https://github.com/mattpocock/skills)。执行 agent（QwenPaw 上的阿泡）在自己的 workspace 里维护 skill 定义，本仓库只承担 skill 的产物：CONTEXT / PRD / ADR / issues。

### Issue tracker

V7 issue 进入新的 `.scratch/scriptflow-v7/`；`.scratch/scriptflow-v5/` 与 `.scratch/scriptflow-v6/` 仅作历史记录。

### Triage labels

用默认的 5 个标签：`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`。详见 [`docs/agents/triage-labels.md`](./docs/agents/triage-labels.md)。

### Domain docs

V7 的领域语言必须在 V7 规格或后续 V7 ADR 中定义。旧根 `CONTEXT.md` 不再具有规范效力。

## 代码约定

### 命名

- Python：`snake_case` 函数 / 变量，`PascalCase` 类，`SCREAMING_SNAKE` 常量
- TypeScript：`camelCase` 函数 / 变量，`PascalCase` 类型 / 组件
- 术语以 V7 规格与 V7 ADR 为准；Script 与 Novel 同名概念也必须位于各自领域命名空间

### 目录

```
agent-script-platform/
├── AGENTS.md              # 你现在看的这份
├── CONTEXT.md             # V5 历史领域语言，不是 V7 依据
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
│   ├── v7-spec-v1.1/      # V7 唯一规格基线
│   ├── PRD-V5.md          # 历史 PRD
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
