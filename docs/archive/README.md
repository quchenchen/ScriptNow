# 归档文档

这些文档是 ScriptFlow 项目 V5 之前的历史思考产出。**它们不再是主线**，但保留在这里作为决策历史参考。

新主线文档：
- [`../../CONTEXT.md`](../../CONTEXT.md)（领域语言）
- [`../PRD-V5.md`](../PRD-V5.md)（主线 PRD）
- [`../adr/`](../adr/)（架构决策）

## 归档内容

| 文件 | 内容 | 归档原因 |
|---|---|---|
| `PRD-V3.md` | V3.0 产品需求文档（2026-07-14），基于 StoryPlay 走查 + Toonflow 分析 + AgentScope 2.0 | 由 PRD-V5 取代。7 阶段流水线定位由 ADR-0001 修正为生长式。 |
| `SPEC-V4.md` | V4.0 产品规格说明书 | 由 PRD-V5 取代。 |
| `PLAN.md` | 早期完整实施方案 | 由新的 vertical slice issues 取代（`.scratch/scriptflow-v5/`）。 |
| `PLAN-V2.md` | 修订版实施方案 | 同上。 |
| `FRAMEWORK-COMPARISON.md` | AgentScope vs LangGraph 选型对比 | 决策已落定（AgentScope），无需再对比。 |
| `AGENTSCOPE-ANALYSIS.md` | AgentScope 2.0 能力深度分析 | 技术参考仍有价值，但不再是主线设计输入。 |
| `SCRIPTFLOW-V2-REVIEW.md` | V2 时期的自评 | 历史。 |

## 什么情况下会翻这些文档？

- **溯源"当初为什么这么设计"** —— 特别是 AgentScope 选型的原始理由
- **产品对标信息** —— PRD-V3 里 StoryPlay / Toonflow 竞品分析仍有参考价值
- **写新 ADR 时** —— 需要引用某个旧决策的具体上下文

但**任何代码 / 命名 / 数据模型的判断，一律以 CONTEXT.md + docs/adr/ 为准**，不以这里为准。
