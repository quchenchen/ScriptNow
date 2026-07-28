# ScriptNow 产品版本与验证记录

## 0.2.0 — 2026-07-29（开发预览）

### 版本定位

`0.2.0` 是统一创作运行内核的开发预览，不是 Release Candidate。版本号同时写入 Python
包、FastAPI OpenAPI、前端 workspace、Creator、Admin 和共享包。

### 本版本纳入

- Creative Operation、Stage、Artifact、Decision 的统一耐久状态。
- Context Manifest 持久化和 operation 绑定。
- 可恢复判定、parked confirmation 数据模型与 AgentScope checkpoint 适配原语。
- Novel、Script、Translation、Recreation 四领域真实 Provider 证据审计命令。
- Skill 基准报告驱动的准入与隔离状态更新。
- 规格索引、业务流程、实施计划和系统升级路线同步更新。

### 自动化门禁

版本整理和归档完成后的完整门禁结果：

- 后端：`315 passed`
- 前端：`55 passed`
- Lint：通过
- Creator/Admin 构建：通过
- `git diff --check`：通过

执行命令：

```bash
make test
make lint
make build
git diff --check
```

Creator 构建仍报告单个压缩后主包超过 500 kB 的性能提示；这不是正确性失败，但应在后续
通过路由级动态加载和图谱/编辑器模块拆包解决。

### 真实 Provider 黄金回放

2026-07-29 在版本整理后再次对现存四领域项目执行
`real-provider-golden-replay/v1`，命令退出码为 `2`，四条场景均未通过：

- Novel：StoryMap decision 非 exactly-once；导出不完整或缺失。
- Script：StoryMap decision、scene write、quality review、packaging、export 不完整。
- Translation：export 不完整。
- Recreation：quality review、packaging、export 不完整。

上述结果是当前发布阻塞项，不允许通过降低完成判定、补造事件或把 partial 标成 success
绕过。成本路由不在本版本研发范围。

本机脱敏证据保存在 Git 忽略目录：

```text
.local/diagnostics/0.2.0-real-provider-replay.json
```

### 归档与清理

- 研究网页、融合调研和阶段性实现审计统一进入 `docs/archive/2026-07-29/`。
- 根目录用户素材和旧数据库快照移入本机 `.local/archives/2026-07-29/`，不再由 Git 跟踪。
- 当前运行数据库仍仅作为本机忽略文件存在，不属于产品版本。
- `.DS_Store`、测试缓存、Ruff 缓存、旧审计临时目录和本地运行日志已从开发树清除。
