# P0-05 冻结 Script 与 Novel 契约

- Label: ready-for-agent
- Status: completed

## 验收

- Script：Episode → Scene → Story Beat 与剧本段落类型。
- Novel：Volume → Chapter → Story Beat 与小说 block 类型。
- 两套 Writer、审读、格式、导出和定位 patch 契约分别定义。
- shared/platform 层不包含任何 Script/Novel 领域枚举。

## 产出

- `docs/v7-spec-v1.1/04-DOMAIN-CONTRACTS.md`
- Script Episode/Scene/Beat、ScriptBlock、ScriptPatch。
- Novel Volume/Chapter/Beat、NovelBlock、NovelPatch。
- schema、cross-domain rejection 与 import boundary 自动化测试。
