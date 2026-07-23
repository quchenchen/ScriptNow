# ScriptFlow V7

V7 独立工程。产品与技术基线见 `../docs/v7-spec-v1.1/`。

## 边界

```text
backend/src/scriptflow_v7/
├── platform/   # 认证、租户、事件、计量、运行时等共享基础设施
├── script/     # 剧本领域
├── novel/      # 小说领域
└── app.py      # composition root，可组装上述模块

frontend/
├── apps/creator/
├── apps/admin/
└── packages/shared/  # 仅共享无领域语义的 UI/API 基础
```

允许依赖方向：

```text
app → platform
app → script → platform
app → novel  → platform
```

禁止 `platform → script|novel`，禁止 `script ↔ novel`，禁止导入 `scriptflow_v6` 或根目录旧 `backend`。

## 验证

```bash
cd backend
python -m pytest

cd ../frontend
npm install
npm run build
```
