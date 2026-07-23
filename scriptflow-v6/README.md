# ScriptFlow V6

全新实现目录。这里不是旧版重构层，也不依赖仓库根部的 `backend/`、`frontend/` 或阶段式 pipeline。

## 边界

- `backend/`：FastAPI + SQLAlchemy，按领域服务组织。
- `frontend/`：Vue 3 + TypeScript，围绕专注创作 / 故事规划 / 审阅决策构建。
- `docs/`：V6 在开发阶段的就地契约。
- `tests/`：只验证公开接口和领域不变量。

首个 vertical slice：Scene 选区 → Revision Brief → Context Pack → Candidate Revision → Adopt / Reject / Stale。

## 运行

```bash
cd scriptflow-v6/backend
../../backend/.venv/bin/pytest
../../backend/.venv/bin/uvicorn scriptflow_v6.main:app --reload --port 8100
```

```bash
cd scriptflow-v6/frontend
npm install
npm run dev
```
