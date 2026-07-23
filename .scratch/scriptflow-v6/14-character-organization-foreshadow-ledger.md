# 14 · 角色、组织关系与伏笔回收账本

- **Status**: done
- **Type**: domain / backend / frontend
- **Blocked by**: 13
- **Blocks**: Continuity Gate, Long-form Writing
- **Est**: L（按实体关系 / 伏笔生命周期 / UI 三个 slice 推进）

## What to build

参考 MuMuAINovel 的长篇连续性机制，为 ScriptFlow 建立可人工维护、可由 Agent 提取候选、采用后进入 Context Pack 的角色、组织、成员关系和伏笔/钩子账本。

## Acceptance criteria

- [x] 创作中可新增 Character 与 Organization
- [x] 支持 Character↔Character、Character↔Organization、Organization↔Organization 关系
- [x] 角色记录位置、情绪、知识、目标、状态来源与最后变化单元
- [x] 伏笔支持 planned/pending/planted/reinforced/partially_resolved/resolved/abandoned
- [x] 记录预设埋入/回收、实际埋入/回收和正文证据
- [x] 临近回收与超期状态进入 Context Preview
- [x] Agent 只能提交候选，采用后才物化为作品事实
- [x] 右栏可创建、查看和处理上述对象
- [x] owner isolation、状态机和上下文回归测试通过
