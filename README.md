# ScriptNow

**AI Agent 团队驱动的剧本与小说创作平台。**

当前产品版本为 **`0.2.0`（开发预览）**。现行应用只有一套，位于
[`scriptnow/`](./scriptnow/)；旧版本执行代码和阶段性研究资料不参与构建、测试或运行。

## 当前基线

- [`docs/v7-spec-v1.1/00-README.md`](./docs/v7-spec-v1.1/00-README.md) — 基线与已批准决策
- [`docs/v7-spec-v1.1/01-PRD-V7.md`](./docs/v7-spec-v1.1/01-PRD-V7.md) — 产品与技术规格
- [`docs/v7-spec-v1.1/02-LEGACY-DECONTAMINATION.md`](./docs/v7-spec-v1.1/02-LEGACY-DECONTAMINATION.md) — 复用、归档与删除规则
- [`docs/v7-spec-v1.1/03-DEVELOPMENT-PLAN.md`](./docs/v7-spec-v1.1/03-DEVELOPMENT-PLAN.md) — 开发与验证计划
- [`docs/v7-spec-v1.1/RELEASE-NOTES.md`](./docs/v7-spec-v1.1/RELEASE-NOTES.md) — 产品版本、验证结果与已知限制
- [`docs/archive/README.md`](./docs/archive/README.md) — 非现行资料归档索引

## 5 分钟启动

```bash
make setup
make dev
```

开发地址：

- 创作端：http://127.0.0.1:5173
- 管理端：http://127.0.0.1:5174
- 后端：http://127.0.0.1:8000

也可以分别启动：

```bash
make backend
make creator
make admin
```

## 工程结构

```text
scriptnow/
├── backend/                # FastAPI + AgentScope + SQLAlchemy/Alembic
│   ├── src/scriptnow/
│   │   ├── platform/       # 共享平台能力
│   │   ├── script/         # 剧本独立领域
│   │   └── novel/          # 小说独立领域
│   └── skills/             # 运行时 Skill 资产
└── frontend/
    ├── apps/creator/       # 创作端
    ├── apps/admin/         # 管理端
    └── packages/shared/    # 无领域语义的共享基础
```

Script 与 Novel 只共享 platform，不共享正文、StoryMap、Writer、审读、格式和导出领域模块。

## 验证

```bash
make test
make lint
make build
```

## 授权

Proprietary. All rights reserved.
