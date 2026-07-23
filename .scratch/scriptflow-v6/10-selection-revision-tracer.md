# 10 · 选区 Revision 创作连续性 Tracer

- **Status**: done
- **Type**: product / backend / frontend
- **Blocked by**: 01, 08
- **Blocks**: Story Core Editor, Ralph Revision, Adaptation Revision
- **Est**: L（按 backend / frontend 两个 slice 交付）
- **Parent PRD**: docs/PRD-V6.md

## What to build

跑通第一条 Creative Continuity Protocol：选区目标形成 Revision Brief 和 Context Pack，Agent 只创建 Candidate Revision；用户比较后采用或拒绝；基线变化时禁止覆盖并要求重新比较。

## Acceptance criteria

- [x] `creative_revisions` 迁移与 ORM 模型
- [x] Scene Candidate Revision 创建、读取、采用、拒绝 API
- [x] Candidate 创建不修改 Scene 正文
- [x] 采用使用内容 hash 检查基线；变化后标记 stale
- [x] 所有端点验证项目所有权
- [x] Revision Brief / Context Pack / evidence / impact 被结构化保存
- [x] 后端完整回归通过
- [x] 编辑器选区生成 Revision Brief
- [x] Compare 展示解决、保留、影响与文本 diff
- [x] 采用、拒绝和 stale 恢复交互
- [x] Living Asset Candidate 提取与 Inbox
