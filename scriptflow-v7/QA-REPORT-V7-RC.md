# ScriptFlow V7 Release Candidate QA Report

版本：v7-spec-v1.1 · 验收日期：2026-07-20 · 环境：macOS / Python 3.12 / SQLite / Vue 3 / Vite 8

## 结论

当前候选版本已通过 P8.5–P8.8 治理闭环、P9 自动化硬化主门禁及 Creator 四组合浏览器回归。Blocker/Critical/High 为 0，达到可完整测试 Release Candidate。

## 自动化证据

| Gate | 当前证据 | 结果 |
|---|---|---|
| Backend unit/domain/API/security/migration | `pytest` 收集 106 项；全套通过 | PASS |
| Python lint | `ruff check src tests migrations scripts` | PASS |
| Frontend unit/component | Vitest 7 files / 13 tests | PASS |
| Creator/Admin production build | `vue-tsc` + Vite | PASS |
| 200 Findings | ReviewPanel 仅渲染 10 条虚拟窗口 | PASS |
| 事件性能 | 1000 事件、20 次增量查询，P95 < 200ms | PASS |
| 无障碍 | axe WCAG 2 A/AA，Admin 登录面无 serious/critical | PASS |
| 数据完整性 | 实际开发库五项差异均为 0 | PASS |
| Backup/Restore | 真实 V7 schema Golden Project 的 hash、事件、余额、工作区记忆一致 | PASS |
| Legacy | V7 runtime/frontend 无 V5/V6 import 或引用 | PASS |
| Production artifact | 无 `.map`、Legacy 标记或凭据模式命中 | PASS |
| 改编素材闭环 | 上传自动解析/索引、租户隔离检索、Creator 引用定位 | PASS |

## P9 对照

| WBS | 证据 |
|---|---|
| P9.1 空态/错误/重试/取消/响应式/无障碍 | Creator/Admin 空态；Dock 取消/恢复；导出失败重试；移动 Admin 导航；axe gate |
| P9.2 性能 | 200 Findings 虚拟化；事件增量 P95；Admin 50/页 |
| P9.3 安全 | 双租户 IDOR、CSRF、refresh 防重放、登录限流、路径穿越、恶意文件隔离、凭据认证加密/不回显 |
| P9.4 故障注入 | 主模型失败 fallback；MCP 断连降级；事务回滚；SSE 重连去重；导出失败可重试 |
| P9.5 数据完整性 | `audit_integrity.py` 检查孤儿快照、跨租户引用、重复用量和重复账本 |
| P9.6 Legacy 清理 | `docs/v7-spec-v1.1/04-LEGACY-CLEANUP-REPORT.md` + import/artifact scan |

## Admin 浏览器验收

已验证租户、用量、Provider/Model/Tier、Agent/Tool、MCP/沙箱、记忆六个视图；角色记忆策略与默认沙箱策略写操作真实持久化。MCP 新发现工具默认拒绝，密钥不回显；空态和移动导航可用。

## Creator 浏览器验收

- 依次验证 Script 原创、Script 改编、Novel 原创、Novel 改编四个既有项目，刷新后项目与领域工作台正确恢复。
- Script 与 Novel 保持独立 StoryMap、正文结构、格式和导出入口；Dashboard 同时显示领域与原创/改编来源。
- 改编项目侧栏已接入“原著引用”区域，支持关键词检索、来源文件/片段标识和原文展开定位；接口测试覆盖索引、命中、删除级联和跨租户拒绝。
- 2048px 宽屏下剧本编辑器约 1278px、正文页约 1218px，无横向溢出；390px 移动视口的隐藏导航不进入可访问树，菜单可展开。测试结束已恢复默认视口。
- “项目控制台”选项已修正为返回 Dashboard；浏览器控制台未观察到阻塞交付的错误。

## 回滚方案

1. 发布前创建 DB + workspace 一致性备份，并记录 SHA-256 manifest。
2. 应用版本回滚不覆盖数据库；若新迁移必须回退，在隔离环境先验证 Alembic downgrade/upgrade。
3. 数据回滚使用 `BackupService.restore` 写入全新目标，校验 SQLite integrity、manifest hash、项目内容 hash、事件和余额后切换。
4. Provider/MCP/模板/工具/记忆策略变更只影响下一次运行；进行中运行继续使用既有 runtime snapshot。

## 已知限制

- 真实外部 LLM/MCP smoke 依赖部署环境凭据，不进入普通 PR 的确定性门禁；当前由 AgentScope contract fake 与真实 MCP client 适配测试覆盖。
- axe 的 jsdom 环境无法计算 canvas 色彩对比；关键 Creator 编辑器已由浏览器视觉 QA 补充核对布局、可见状态和响应式行为。
- 真实外部 Provider 的凭据 smoke 仍是部署环境发布前检查项；其缺失不影响本地确定性 RC 门禁。
