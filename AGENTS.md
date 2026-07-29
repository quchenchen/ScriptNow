# AGENTS.md — ScriptNow Agent 协作约定

任何 AI Agent 在这个仓库中工作前，先读本文件。

## 唯一开发基线

ScriptNow 是全新产品开发，当前唯一有效基线：

1. [`docs/v7-spec-v1.1/00-README.md`](./docs/v7-spec-v1.1/00-README.md)
2. [`docs/v7-spec-v1.1/01-PRD-V7.md`](./docs/v7-spec-v1.1/01-PRD-V7.md)
3. [`docs/v7-spec-v1.1/02-LEGACY-DECONTAMINATION.md`](./docs/v7-spec-v1.1/02-LEGACY-DECONTAMINATION.md)

旧版本材料只可用于有明确目标的历史研究，不得反推当前需求，也不得被当前代码直接导入。复用必须先完成契约对照和 characterization test。

Script 与 Novel 是独立产品领域，只共享 platform；禁止共享正文、StoryMap、Writer、审读、格式和导出领域模块。

## 当前目录

```text
agent-script-platform/
├── AGENTS.md
├── README.md
├── Makefile
├── docs/
│   └── v7-spec-v1.1/       # 唯一规格基线与迁移证据
└── scriptnow/              # 唯一可执行应用
    ├── backend/
    │   ├── src/scriptnow/
    │   │   ├── platform/
    │   │   ├── script/
    │   │   └── novel/
    │   ├── skills/
    │   └── tests/
    └── frontend/
        ├── apps/creator/
        ├── apps/admin/
        └── packages/shared/
```

当前 Python 包名、前端 workspace scope、环境变量前缀和产品标识统一使用 `scriptnow` / `ScriptNow` / `SCRIPTNOW_`。只允许在迁移兼容代码和历史文档中出现旧名称。

## 技术栈

- Backend：FastAPI + AgentScope 2.0 + SQLAlchemy/Alembic + SQLite
- Frontend：Vue 3 + Vite + TypeScript
- Package management：Python `pyproject.toml` + `uv.lock`，前端 npm workspaces

## 代码约定

- Python：`snake_case` 函数/变量，`PascalCase` 类，`SCREAMING_SNAKE` 常量
- TypeScript：`camelCase` 函数/变量，`PascalCase` 类型/组件
- 领域术语以现行规格或后续 ADR 为准
- 新配置必须来自设置、数据库策略、项目参数或 Agent 交互，不得把业务预算、篇幅、章节数、模型或产品策略写死在代码中
- 不得以“降级成功”掩盖契约、结构化输出或 AgentScope block 解析错误

## 测试

- 后端：`scriptnow/backend/tests/test_*.py`
- 前端：`scriptnow/frontend/**/*.spec.ts`
- 只测 public interface，不把 implementation detail 固化进测试
- 变更前后至少运行相关测试；跨层改动运行 `make test && make lint && make build`

## 敏感信息

- `.env*`、数据库、上传文件、密钥与运行日志不得提交
- 不输出或提交 API key、JWT secret、用户素材中的私密信息
- 生产 secrets 只走环境变量或密钥管理

## Git 与清理

- 所有 commit message 必须使用英文，建议采用简洁的祈使句并准确描述变更
- 不 amend 已 push 的提交，不 force push main
- 删除历史实现前先生成可验证归档
- 开发树内不保留可执行旧版本、重复依赖目录或真实运行数据库

## 常用命令

```bash
make setup
make dev
make test
make lint
make build
```
