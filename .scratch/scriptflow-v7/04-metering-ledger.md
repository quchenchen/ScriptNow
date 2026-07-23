# P0-04 计量与额度账本

- Label: ready-for-agent
- Status: contract-complete-persistence-pending-p1

## 验收

- Agent 运行使用 reserve → finalize/release 状态机。
- 并发请求不会重复占用或击穿余额。
- run_id/call_id/idempotency_key 防止重复入账。
- fallback、失败、取消、超时和冲正均有测试。
- 每笔用量保存模型、价格、币种与配置版本快照。

## 已完成

- V7 ADR-0003 冻结 reserve/finalize/release/reverse 与幂等规则。
- 可执行内存状态机覆盖并发争用、月额度优先、失败释放、未用退款、冲正和重放。

## P1 实施项

- SQLite 短事务、表结构、行版本与 call price snapshot。
- 并发压力阈值和 PostgreSQL 迁移触发条件。
