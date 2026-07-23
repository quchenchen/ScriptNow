# 19 · ReMe Agent 记忆体系评估

- **Status**: deferred
- **Trigger**: V6 Creator Gates A–F 完成并通过运行验证后
- **Reference**: https://github.com/agentscope-ai/ReMe

## Evaluation boundary

不在当前产品闭环尚未稳定时直接引入。完成 V6 后评估 ReMe 是否应承担 Agent 工作记忆、跨任务召回或记忆压缩；不得取代创作者确认的 Story Bible、连续性账本和 Candidate → Adopted 权威边界。

## Questions

- ReMe 的 memory unit、召回和更新策略如何映射 Project / Chapter / Scene scope？
- 是否保留来源、版本、采用者和正文证据，满足 lineage 与审计？
- 未确认候选能否被物理隔离，避免召回后变成隐性事实？
- 与当前 Context Pack 组装、Narrative Entity、Foreshadow Ledger 的职责如何分层？
- AgentScope 原生集成能减少多少自维护代码，迁移与运行成本是什么？

## Gate

用同一组连续创作样例对比“当前显式账本”“ReMe 辅助召回”“混合方案”，只在可追溯性、连续性命中率和创作者可控性同时提升时采纳。
