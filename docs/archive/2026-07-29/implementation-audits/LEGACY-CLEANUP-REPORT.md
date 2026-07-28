# ScriptNow Legacy 最终清理报告

版本：2026-07-20 · 状态：RC gate passed

## 范围与结论

V7 可执行代码仅位于 `scriptnow/backend/src/scriptnow`、`scriptnow/frontend/apps/creator/src` 和 `scriptnow/frontend/apps/admin/src`。自动化架构测试扫描 Python/TypeScript/Vue/JavaScript 文件，禁止 `scriptflow_v6`、`scriptflow-v6`、`backend.app` 引用；当前结果为零违规。

Script 与 Novel 继续使用独立的领域 package、数据模型、正文块契约、StoryMap、写作、审读、版本和导出实现，只共享 platform 层。跨域 Python import 与 Novel 前端导入 Script capability 均由 `test_import_boundaries.py` 阻断。

## 处置清单

| 资产 | 处置 | 防污染措施 |
|---|---|---|
| 根目录旧后端、旧前端、V5/V6 文档、旧设计与录屏 | 打包后移出开发树 | 外部归档 + SHA-256 校验 |
| V7 `__pycache__`、pytest/ruff cache、前端 `dist`、`node_modules` | 本地可再生资源，不纳入版本控制 | 根 `.gitignore` |
| V7 开发数据库、工作区、上传、日志和 `.env` | 本地运行资源，不纳入版本控制 | 根 `.gitignore` + 生产 secret 校验 |
| 原型冻结副本 | 仅作为视觉验收参考，不由运行时代码 import | 构建制品扫描 |
| Mock Run | 明确标识为 Mock 测试流程，用量页显示 Mock chip | API/界面显式命名，不伪装真实支付或模型调用 |

## 验证命令

```bash
cd scriptnow/backend
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_import_boundaries.py -q

cd ../frontend
npm run build
find apps -path '*/dist/*' -type f -name '*.map'
```

生产构建当前无 source map、无 Provider/MCP 明文凭据。2026-07-23
完成名称与开发树净化：

- 唯一产品名、Python 包、npm scope、环境变量前缀统一为
  `ScriptNow` / `scriptnow` / `@scriptnow` / `SCRIPTNOW_`。
- 旧事件、旧 Skill 元数据和旧浏览器偏好仅保留读取迁移，不再产生旧名称写入。
- 全量归档 `ScriptNow-pre-purification-20260723-2215.tar.gz` 的
  SHA-256 为
  `8f7b56d78152c2562afda0020dac7307eeff95974ec0601951846ada0572abbb`。
- 旧执行代码和历史资料另存于同目录隔离区
  `ScriptNow-legacy-quarantine-20260723-2215/`。

开发树只保留当前应用、当前规格和空白 ScriptNow issue tracker；防污染同时由物理隔离和自动门禁保证。
