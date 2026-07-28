# 四领域黄金流程与完成基线

| | |
|---|---|
| 版本 | v1.0 |
| 日期 | 2026-07-28 |
| 状态 | 阶段 0 实施中 |
| 关联 | `17-SYSTEM-UPGRADE-ITERATION-ROADMAP.md`、`19-SYSTEM-BUSINESS-FLOW-MAP.md` |

> 本文中的 2026-07-28 审计矩阵是阶段 0 初始快照，不代表当前工作树已经通过真实 Provider
> 全流程验收。能力现状以最新可重放证据包和自动化测试为准，目标业务路径见
> `19-SYSTEM-BUSINESS-FLOW-MAP.md`。

## 1. 目的

本基线把“接口返回了”“Agent 回复了”“事件结束了”和“作品产物真正完成了”分开。
Novel、Script、忠实翻译、故事归化继续拥有独立领域流程，但使用同一套研发审计语言：

```text
operation succeeded
  ⇔ 所有必需 stage succeeded
  ∧ 每个必需领域产物已经落盘
  ∧ 产物可以重新读取
  ∧ 产物能够被下一阶段消费
  ∧ 必需人工决定被持久化且恰好解析一次
```

任何一步不满足，运行只能是 `waiting`、`partial`、`failed` 或 `cancelled`。运行状态先被写成
`succeeded`、之后才发现产物缺失时，审计报告必须标记 `false_success`。

## 2. 四个黄金场景

机器可读场景位于：

```text
scriptnow/backend/golden/creative-flow-v1/
├── novel-original.json
├── script-original.json
├── faithful-translation.json
└── cross-cultural-recreation.json
```

场景文件只声明稳定的领域阶段、产物类型和人工决定边界。模型、篇幅、章节或场次数、语言、
目标市场、预算和质量阈值不得进入黄金执行器代码；它们必须由真实项目契约、平台策略或
Agent 交互提供，并随运行证据保存。

四条路径分别验证：

1. Novel：创意、小说蓝图、小说 StoryMap、章节候选、审读、小说包装和小说导出；
2. Script：创意、剧本蓝图、剧本 StoryMap、场次候选、剧本审读、剧本包装和剧本导出；
3. 忠实翻译：源文导入、章节译文、术语确认、历史快照和译文独立导出；
4. 故事归化：源作分析、目标契约、策略、试写、整书蓝图、生产单元、文化审读、包装和导出。

场景之间不得共享正文、StoryMap、Writer、审读、包装或导出产物类型。

## 3. 运行证据

每次真实重放生成一个 `creative-flow-observation/v1` JSON。证据必须来自真实 API、数据库和
artifact 读取验证，不能手工补造成功事件。最小内容包括：

- scenario id 与 operation id；
- 每个 stage 的状态、首状态、首个可读内容、完成耗时和 token；
- 每个 artifact 的 id、kind、revision、落盘、可读和下一阶段可消费验证；
- 每个 DecisionRequest 的 request id、是否解决及解决次数；
- 失败时的统一错误类别。

统一错误类别为：

- `contract_validation`
- `provider`
- `timeout`
- `persistence`
- `projection`
- `confirmation`
- `cancellation`
- `recovery`
- `domain_quality`
- `unknown`

原始 Provider、Pydantic 或数据库异常保存在受限诊断证据中，不能直接成为作者界面文案。

## 4. 审计入口

校验黄金场景契约：

```bash
make golden-contracts
```

审计单次真实运行：

```bash
cd scriptnow/backend
.venv/bin/python scripts/audit_creative_flows.py \
  --scenario golden/creative-flow-v1/novel-original.json \
  --observation /path/to/real-observation.json \
  --output /path/to/audit-report.json
```

报告固定使用 `creative-flow-audit/v1`，包含：

- 是否通过；
- 完成不变式是否满足；
- 首状态、首内容、总耗时、输入与输出 token；
- 可定位到 stage 的错误和警告。

命令返回非零表示黄金路径未通过，CI 或研发验收不得忽略。

从现有数据库只读采集证据：

```bash
cd scriptnow/backend
.venv/bin/python scripts/collect_creative_flow_evidence.py \
  --scenario golden/creative-flow-v1/novel-original.json \
  --project-id <project-id> \
  --output /path/to/real-observation.json
```

采集器只承认已经落盘且能够重新读取的领域记录。不存在关联 `ProjectRun` 时，operation id
使用明确的 `untracked-project:<project-id>` 诊断标识，并把整体状态保持为 `partial`；
它不会补造运行事件、耗时、token 或成功状态。当前数据库尚不能证明的 StoryMap 独立确认、
剧本审读、忠实翻译导出清单、归化包装与归化导出会在报告中保持缺失，作为下一阶段修复输入。

也可以用单条命令完成“采集 + 审计”：

```bash
make golden-audit-project \
  SCENARIO=script-original \
  PROJECT_ID=<project-id> \
  OUTPUT_DIR=/tmp/scriptnow-golden-audit
```

`SCENARIO` 只能取四个黄金场景文件名（不含 `.json`）。命令在发现断点时返回非零，同时仍会
把 observation 与 audit JSON 写入指定目录，便于修复后对比。`OUTPUT_DIR` 必须显式提供，
避免把真实项目运行证据误提交到开发树。

## 5. 首次真实项目审计

2026-07-28 对现存四领域项目执行只读审计，得到以下可复现矩阵：

| 领域 | 已证明可消费的前序流程 | 当前断点 |
|---|---|---|
| Novel 原创 | 创意、蓝图、StoryMap、章节、审读、包装 | StoryMap 无独立确认谱系；导出清单缺失 |
| Script 原创 | 创意、蓝图、StoryMap | StoryMap 无独立确认谱系；场次正文、剧本审读、包装、导出缺失 |
| 忠实翻译 | 源文、章节译文、术语确认、历史快照 | 独立译文导出清单缺失 |
| 故事归化 | 源作分析、目标契约、策略、试写、蓝图、生产单元 | 文化质量报告、包装、导出缺失 |

因此这些项目均不能被认定为“完整流程成功”。审计分别报告 Novel 3 项、Script 10 项、
忠实翻译 2 项、故事归化 6 项错误。后续修复应补齐领域产物和决定谱系，而不是增加前端
成功提示、合成事件或对缺失阶段做静默降级。

## 6. 阶段 0 剩余工作

当前已完成场景契约、完成判定、错误分类、报告格式、执行命令和 public-interface 测试。
四领域脱敏成功夹具以及 timeout、cancel、recovery、refresh 重复身份故障夹具已进入自动测试；
这些夹具只验证审计契约，不冒充真实 Provider 重放证据。
阶段 0 尚有以下真实运行工作：

1. 将四个脱敏契约夹具升级为可调用真实 Provider 的临时数据库项目，不提交源素材、密钥、
   数据库或真实运行日志；
2. 执行四条完整路径并保存基线报告；
3. 将已经进入 public-interface 自动测试的刷新去重、取消、Provider 超时和服务重启状态
   收敛，升级为四领域真实 Provider 故障注入；平台层目前已保证超时使用稳定错误码、
   额度释放和终止事件落盘，重启后 `queued` / `running` 转为可重试
   `runtime_interrupted`，`waiting` 决定上下文保持可恢复；
4. 将人工修改量与有效产物成本加入报告，但不设置未经数据验证的硬阈值；
5. 修复只读采集已经揭示的运行谱系与领域产物缺口。

完成以上工作并实现一次命令重放四个真实项目后，阶段 0 才能转为完成并进入阶段 1。

这里的“重启恢复”不等于伪装续跑：在 `Checkpoint` 和 AgentScope `AgentState` 尚未持久化前，
进程退出时正在执行的协程必须被明确标记为中断并由用户或调度器重试。只有从已验证
checkpoint 恢复且不会重复产生副作用，才可计为真正恢复成功。
