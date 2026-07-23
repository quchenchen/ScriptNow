# ScriptFlow V6 实施完成性审计

- **Date**: 2026-07-16
- **Basis**: PRD-V6、PLAN-V6、创作者中心纠偏方案、当前代码、测试与本地预览
- **Verdict**: Gate A 已通过；Gate B 已通过首个完整传播 Gate；Gate C 主闭环已实现但双媒介浏览器 E2E 尚未完成；Gate D～F 未通过

## 0. 持续复审更新（2026-07-16）

本文件后续章节保留首次审计基线；以下复审以当前工作树、自动化测试和运行预览为准，覆盖其中已经被实现反证的旧结论。

| Creator Gate | 当前结论 | 权威证据 |
|---|---|---|
| A · 项目计划与作品目录 | **通过** | Project Plan 持久化；目标规模影响预览；Volume/Chapter 与 Episode/Scene Story Map CRUD/排序；Vue Router 深链和刷新恢复；StoryCatalog 组件测试与运行预览 |
| B · 故事圣经与传播 | **通过 tracer gate** | 四类 Story Bible Change；生效范围；逐单元影响；stale；同单元 Revision Task；未来 Context；Cascade Revision；正文证据；`test_story_bible_propagation.py` |
| C · 正文编辑与版本 | **运行 Gate 通过，CI E2E 待 Gate F** | 隔离数据库真实完成 Chapter/Scene 创建、采用、编辑、元数据、刷新恢复、AI 拒绝与历史回退；乐观锁、六类 AI 选区、可中断 NDJSON；16 项前端与 26 项后端测试 |
| D · 原创剧本专业闭环 | **未通过** | 缺完整 Structure/Beat/Episode Plan、Ralph rubric、Script Sheet、DOCX、Branch/Growth Tree 的可运行整链 |
| E · 小说改编剧本 | **未通过** | Source Canon 解析、章节检索、Adaptation Map、来源对照和改编 rubric 尚未形成 Gate 样例 |
| F · 发布 | **未通过** | 正式迁移、认证、统一错误恢复、浏览器 E2E、性能、埋点和真实项目试用尚未完成 |

Gate B 当前证明的创作者闭环：

```text
填写“二丫第 9 章以对手身份出场”
→ 预览第 9 章候选、第 10～12 章计划和第 1～8 章保护范围
→ 创作者确认后写入角色与关系
→ 第 9 章旧候选 stale，并以同一章 Revision Task 重新交付
→ 交付返回“二丫”在正文中的字符位置和证据片段
→ 第 10 章 Context 自动继承
→ 已采用正文只生成可比较 Cascade，采用后才产生新版本
```

## 1. 审计口径

只有同时具备领域持久化、公开 API、创作者可理解的 UI、关键状态处理和自动化测试，才算产品能力完成。只有表、接口、演示文案或手动可点击状态，记为“技术原型”。

## 2. 当前可保留的能力

| 能力 | 当前证据 | 结论 |
|---|---|---|
| Story Core 候选与采用 | StoryCoreCandidate、Agent Task、采用 API | 技术原型 |
| 正文候选与采用 | ManuscriptUnit/Candidate、连续生成 API | 技术原型 |
| Scene 选区 Revision | hash stale 检查、adopt/reject | 可复用 tracer |
| 连续性账本 | 人物/组织/关系、伏笔状态机、Context Preview | 后端基础可复用；UI 待重做 |
| Context Pack | Story Core、上一单元、人物、关系、伏笔、指令 | 组装器可复用；demo runtime 未完整消费 |

## 3. Gate 审计

### Gate 0 · 产品契约

**基本通过。** PRD、领域语言、ADR、交互宪法和纠偏方案存在。纠偏方案成为后续生产实现优先依据。

### Gate 1 · 项目创建与工作台

**未通过。**

- Project 没有 `creation_source`、`delivery_medium`、`seed_maturity` 的正式字段与迁移。
- 创建向导没有目标规模、创作方式、风格边界、改编权利确认和草稿恢复。
- 没有 Project Plan。
- 没有真实 Volume/Chapter 或 Episode/Scene Story Map。
- 没有 Vue Router、深链与刷新位置恢复。
- Dashboard 没有真实正文目标、质量、风险和 Agent 汇总模型。
- 前端只有纯函数测试，没有 App、创建、路由和媒介适配测试。

### Gate 2 · Story Core、编辑器与 Revision

**未通过。**

- 缺 Premise、World、Timeline Event、Story Beat、Plot Thread、Style Profile、Source Reference 的完整模型与编辑 UI。
- 人物/组织/关系只有新增和列表原型，没有人物卡、轨迹、编辑、冻结、来源与影响。
- 正文是 readonly textarea；没有直接编辑、autosave、保存状态、冲突保护和离开提醒。
- Revision 只支持 Script Scene 选区，没有 Chapter、通用快照、历史、回滚和 Branch。
- Story Bible 变化不会标记候选 stale、计算影响或创建 Cascade Revision。

### Gate 3 · 原创剧本闭环

**未通过。**

- 缺 Structure、Story Beat、Episode Plan、Scene Intent 与血缘。
- 生成器只会顺序产生单个 Scene/Chapter，不按项目计划生成三集剧本。
- demo runtime 不消费人物、关系和伏笔上下文。
- 缺 Ralph Loop UI、证据化审稿、格式检查接入、Script Sheet 和 DOCX 导出。
- 缺完整 Agent Activity、Delivery 和 Decision 对象。
- 缺 Branch、Growth Tree、Dirty、Cascade。

### Gate 4 · 小说改编剧本闭环

**未通过。**

- Source Canon 只保存文本/文件名，没有真实上传、解析、章节目录、检索和恢复。
- 缺 Source Reference、Adaptation Map、忠实度策略和来源对照。
- 缺人物偏移、情节遗漏、来源冲突和媒介转换 rubric。

### Gate 5 · 发布准备

**未通过。**

- 无正式迁移体系；运行时依赖 `create_all`。
- 本地 demo user 替代认证与真实 owner 边界。
- 无统一错误、重试、undo、unsaved、可访问性验证。
- 无端到端测试、性能测试、埋点、真实试用和发布流程。
- 前端集中在一个 App.vue，缺路由、组件边界和 API client。

## 4. 关键技术债务

1. `ManuscriptUnit` 与 `Scene` 重复表达正文对象。
2. CreativeDirective 的目标元数据编码在 `constraints_json`，需要正式迁移。
3. Living Asset Candidate 的提取为关键词启发式，不是结构化 Skill 输出。
4. demo runtime 与真实 runtime 消费契约不同，造成假闭环。
5. 当前 Preview 会在最新单元未采用时提前显示下一 ordinal。
6. 伏笔 `NarrativeThread` 与 `ForeshadowRecord` 仍有双轨语义。
7. API 多处依赖 demo user，部分服务没有统一 owner guard。
8. 前端存在生成遗留 `App.vue.js` / `main.js`，源码组织未收敛。

## 5. 新关键路径

```text
Project Plan + 目标规模
→ 真实 Story Map
→ Story Bible 主工作区
→ Chapter/Scene Intent + 可编辑正文
→ Story Bible 传播与 Revision
→ 原创剧本审稿与导出
→ Source Canon / Adaptation Map
→ 发布验收
```

任何新 Agent、图表或抽象管理面板，若不能推进上述路径，不得插队。
