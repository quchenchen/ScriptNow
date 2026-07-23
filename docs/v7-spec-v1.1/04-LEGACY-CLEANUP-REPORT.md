# ScriptFlow V7 Legacy 最终清理报告

版本：2026-07-20 · 状态：RC gate passed

## 范围与结论

V7 可执行代码仅位于 `scriptflow-v7/backend/src/scriptflow_v7`、`scriptflow-v7/frontend/apps/creator/src` 和 `scriptflow-v7/frontend/apps/admin/src`。自动化架构测试扫描 Python/TypeScript/Vue/JavaScript 文件，禁止 `scriptflow_v6`、`scriptflow-v6`、`backend.app` 引用；当前结果为零违规。

Script 与 Novel 继续使用独立的领域 package、数据模型、正文块契约、StoryMap、写作、审读、版本和导出实现，只共享 platform 层。跨域 Python import 与 Novel 前端导入 Script capability 均由 `test_import_boundaries.py` 阻断。

## 处置清单

| 资产 | 处置 | 防污染措施 |
|---|---|---|
| 根目录 V5/V6 文档与 `scriptflow-v6/` | 保留为历史研究资料，不进入 V7 构建 | AGENTS 基线 + Legacy 扫描 |
| V7 `__pycache__`、pytest/ruff cache、前端 `dist`、`node_modules` | 本地可再生资源，不纳入版本控制 | 根 `.gitignore` |
| V7 开发数据库、工作区、上传、日志和 `.env` | 本地运行资源，不纳入版本控制 | 根 `.gitignore` + 生产 secret 校验 |
| 原型冻结副本 | 仅作为视觉验收参考，不由运行时代码 import | 构建制品扫描 |
| Mock Run | 明确标识为 Mock 测试流程，用量页显示 Mock chip | API/界面显式命名，不伪装真实支付或模型调用 |

## 验证命令

```bash
cd scriptflow-v7/backend
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_import_boundaries.py -q

cd ../frontend
npm run build
find apps -path '*/dist/*' -type f -name '*.map'
```

生产构建当前无 source map、无 Legacy 标记、无 Provider/MCP 明文凭据。历史资产未物理删除，因为它们处于 V7 构建边界之外且 AGENTS 约定要求保留参考；防污染由自动门禁保证，而非依赖人工记忆。
