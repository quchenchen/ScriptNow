# V7 Script / Novel 领域契约

## 共享边界

两领域只共享 platform 的 identity、run、event、usage、workspace 与 observability。StoryMap、正文块、Writer 输入输出、审读 patch 和导出模型不共享。

## Script

```text
Episode → Scene → ScriptStoryBeat
ScriptDocument → ScriptBlock[]
ScriptPatch(base_revision_id, para_id, expected_text, replacement[])
```

Block：`slugline/action/character/dialogue/transition`。

格式：`chinese/hollywood`，项目创建后锁定。

## Novel

```text
Volume → Chapter → NovelStoryBeat
NovelDocument → NovelBlock[]
NovelPatch(base_revision_id, block_id, expected_text, replacement[])
```

Block：`heading/prose/dialogue/quote/divider`。

Novel 不拥有 script_format、Episode、Scene、duration_seconds 或 para_id。

## Patch 不变式

1. `base_revision_id` 必须等于当前 adopted revision。
2. anchor ID 必须存在，`expected_text` 必须与当前文本一致。
3. 不满足前置条件时 Finding/编辑候选进入 stale 或 conflict，不自动模糊套用。
4. patch 应用与新 revision、Finding 状态、decision event 在同一事务提交。
5. 重复 idempotency key 返回第一次结果。
