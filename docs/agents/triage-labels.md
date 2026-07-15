# Triage Labels

在 issue 文件的 `Status:` 字段里用以下值之一。

| 标签 | 意思 | 谁能拿起来 |
|---|---|---|
| `needs-triage` | 有人报了个 issue，还没被分类 | 维护者（Q老师）review |
| `needs-info` | 等报告者补充信息 | 报告者 |
| `ready-for-agent` | 完整规格已就绪，agent 可以离线 (AFK) 接单 | 任意 agent |
| `ready-for-human` | 需要人做（涉及产品决策 / 敏感 / UI 试错） | Q老师 |
| `wontfix` | 决定不做 | — |

其他有用的 status（非 triage，是执行状态）：

| 状态 | 意思 |
|---|---|
| `proposed` | 刚提出，还没 triage |
| `in-progress` | agent 或人正在做 |
| `blocked` | 卡在依赖上（应该配合 `Blocked by:` 字段） |
| `done` | 完工，`Acceptance criteria` 全 √ |
