# V7 ADR-0003：事务化额度预留与不可变账本

- Status: Accepted
- Date: 2026-07-18
- Scope: V7 only

## Decision

生成运行不得使用“检查余额→运行→事后扣费”。统一状态机：

```text
reserve → finalize
        ↘ release
finalize → reverse
```

- `reserve` 在同一事务内锁定账户、检查余额、按“月度额度→同等级点数”分配并扣除可用余额。
- `(tenant_id, idempotency_key)` 唯一；重复 reserve 返回原预留。
- `finalize(actual_tokens)` 记录实际消耗并退回未使用预留；实际消耗不得超过预留。
- 失败、取消、超时走 `release`；已完成运行的人工/系统冲正走 `reverse`，不得删除原记录。
- 每个 model call 以 `(run_id, framework_event_id)` 唯一记录；fallback/retry 分别计量。
- 每笔记录冻结 tier、模型、价格、币种和 runtime config version；后续改价不改变历史成本。

SQLite 实现使用短写事务与账户行版本；并发压力超过 P1 定义阈值时迁移 PostgreSQL，不通过应用级“先查后写”补丁规避。
