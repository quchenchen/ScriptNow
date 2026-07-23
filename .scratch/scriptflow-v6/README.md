# ScriptFlow V6 · Issue Tracker

V6 主线：双维度项目模型 → 动态工作台 → Story Core/Manuscript/Revision → 原创剧本闭环 → 小说改编剧本闭环。

```text
01 产品契约（done） → 08 产品与交互蓝图（done）
  ├─→ 02 项目字段迁移 → 03 四类创建入口 → 04 动态工作台壳 → 05 Dashboard
  ├─→ 06 前端 Vitest 基线 ───────────────┘
  └─→ 07 V5 #11 收口（done）
  └─→ 10 选区 Revision tracer（done）
       └─→ 11 上下文指令器（done）
            └─→ 12 右侧创作协作栏（done）
                 └─→ 13 下一单元 Context Preview（done）
                      └─→ 14 角色/组织/关系/伏笔账本（done）
15 创作者中心产品纠偏（ready；替代 11～14 的右栏呈现，保留后端能力）
  └─→ 16 故事圣经到正文传播契约（ready；修复“设定已保存但创作未生效”）
17 Project Plan + Story Map tracer（done；新执行关键路径起点）
  ├─→ 17A Project Plan（done）
  ├─→ 17B 真实 Story Map（done）
  └─→ 17C 可深链工作台（done）
       └─→ 18 LLM 正文编辑器闭环（ready；Vue 编辑层 + 内核无关 Revision 协议）
```

规范沿用 [`docs/agents/issue-tracker.md`](../../docs/agents/issue-tracker.md)。每个 issue 必须包含用户可见验收，不允许把必要 UI 延期到未定义批次。
