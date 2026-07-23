# P0-06 旧资产复用与清理清单

- Label: ready-for-agent
- Status: inventory-complete-migrations-tracked-by-owning-phases

## 验收

- 每个 V5/V6 模块标记 reuse/migrate/isolate/archive/delete。
- reuse/migrate 项有 characterization test 和 V7 契约对照。
- V7 不直接 import legacy 路径。
- 删除项通过引用扫描；清理后后端测试、前端测试和双 SPA build 通过。

## 产出

- `docs/v7-spec-v1.1/references/LEGACY-INVENTORY.md`
- V6 23 个 Python 模块、4 组 skills、tests、root V5 backend、两套 frontend 与文档全部分类。
- 业务源码的实际迁移/删除由对应 P1–P9 work package 在替代实现验证后完成。
