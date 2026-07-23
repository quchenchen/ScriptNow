# ScriptFlow V7 小说 Skill 体系审计与建设方案

版本：2026-07-22  
范围：Novel 领域；Script 领域不在本轮范围内。

## 1. 结论

现有运行时具备 Skill 文件目录、AgentScope loader、角色核心绑定和按题材/主题/风格/结构选择的基础，但此前只有通用 Skill 与两个窄题材包，尚不能称为健全的小说 Skill 系统。主要缺口是：

- 缺平台策略层，番茄类中文连载与海外英文连载没有独立读者契约。
- 缺语言与目标平台选择维度，中文规则可能误入英文项目。
- 主流类型覆盖不足，类型惯例、故事引擎、风格参考和失败模式未结构化。
- 质量标准分散，缺统一的证据化审校门槛。
- 外部素材库成熟度不一，缺准入、隔离、版本与验证机制。

本轮采用可组合四层架构：核心角色 Skill + 平台 Skill + 主要类型 Skill + 统一质量 Skill。每一层只负责一种决策，避免巨型 prompt 互相覆盖。

## 2. 当前运行时改造

`CreativeProfile` 新增 `platforms`，`SkillDescriptor` 新增 `platforms` 与 `languages`。Resolver 先做语言资格过滤，再按平台、题材、主题、风格与结构加权选择。未明确平台时采用产品偏好默认值：中文为 `fanqie`，英文为 `global-serial`；项目显式选择始终覆盖默认值。

选择组合示例：

| 项目 | 自动组合 |
|---|---|
| 中文、番茄、都市脑洞/系统 | `novel-write` + `novel-platform-fanqie` + `novel-cn-urban-power` + `novel-serial-quality-review` |
| 英文、Webnovel、狼人爱情 | `novel-write` + `novel-platform-global-serial` + `novel-en-paranormal-romance` + `novel-serial-quality-review` |

## 3. 新增分类 Skill

### 平台层

- `novel-platform-fanqie`：中文移动端免费连载的作品承诺、早期冲突、章节推进与长线引擎。
- `novel-platform-global-serial`：Wattpad、Webnovel、Dreame、GoodNovel、Radish、Inkitt 类英文移动连载。

平台 Skill 不固化榜单、福利、收益、固定更新字数或活动规则；这些信息变化快，应在发布阶段实时核验。番茄官网当前同时展示都市高武、东方仙侠、现言脑洞、宫斗宅斗、科幻末世、历史古代、都市脑洞和都市日常等动态分类，说明平台类型应作为可演进路由而非永久枚举。

### 中文类型层

- `novel-cn-urban-power`：都市脑洞、都市日常、都市高武、神豪、职场、现实、系统。
- `novel-cn-fantasy-progression`：玄幻、仙侠、修炼、升级、东方玄幻、系统。
- `novel-cn-romance-relations`：现代/古代言情、豪门婚恋、甜宠虐恋、宫斗宅斗。
- `novel-cn-suspense-survival`：悬疑推理、末世、无限流、规则怪谈与生存。

### 英文类型层

- `novel-en-commercial-romance`：contemporary、billionaire、mafia、dark、college、marriage、romantic suspense。
- `novel-en-paranormal-romance`：werewolf、vampire、paranormal romance、romantasy 与 gothic bond。
- `novel-en-speculative-serial`：fantasy、science fiction、dystopian、adventure 与 progression。
- `novel-en-mystery-thriller`：mystery、thriller、crime、horror 与 detective。

### 质量层

- `novel-serial-quality-review`：统一检查作品承诺、人物能动性、场景因果、人物连续性、世界连续性、叙述声音、文本肌理和连载推动。

## 4. `/Users/quchenchen/Documents/github/novel-skills` 成熟度审计

该目录共约 1600 个文件，是混合素材库，不是可直接安装的 Skill 仓库。当前分级如下。

### A 级：方法成熟，可拆解吸收

- `novel-book-dissector`：多维拆书、结构与人物模式提取有价值。吸收“提取机制而非复刻内容”的原则，后续应成为独立的作品蒸馏 Skill。
- `novel-style-learner`：句式、词汇、对白、氛围、情节、节奏六维画像方向正确。需要加入版权边界，输出可解释的特征档案而非作者模仿。
- `novel-auditor`：人物、因果、时间线、伏笔、视角和重复表达的检查维度成熟。旧实现过度依赖 grep 与文件目录，应迁移为事实图谱和版本化正文检查。

### B 级：局部成熟，需重构后使用

- `gothic-novel-adapter`、`werewolf-vampire-novel`：题材工作流与迭代思想可用，但包含固定世界、固定轮次、固定字数和项目专属样例。已抽象进 gothic-bond 与 paranormal-romance Skill，不复制具体设定。
- `novel-sidekick-enhancer`：强调配角拥有弧线是正确的，但“四步且体面退出”过度模板化。吸收为配角能动性检查，不作为固定剧情生成器。
- `western-novel-adapter`：可读性和本地化意识可用；“欧美统一短句/固定章节长度”不成立，改用语言、类型与目标平台组合。
- `fanqie-novel`：早期承诺、冲突和获得感可用；固定 300/500/1000 字规则只可作为诊断启发，不能成为硬门槛。
- `novel-studio`：阶段协调和完成度检查可参考，但绑定 Obsidian 文件树与 shell 命令，不兼容 V7 的数据库事实、候选版本和 AgentScope 事件流。

### C 级：素材/案例，不进入运行时

- 已完成小说、DOCX、改编报告、项目模板和 `haiwai` 内容：用于回归测试或人工研究，不作为自动注入上下文。
- `AI小说提示词` 与通用指令合集：粒度、重复度、来源与质量不一，只能按主题抽样评估。

### Q 级：隔离区

- 包含非自愿、乱伦、奴役、人格贬损、危险性行为等极端内容的提示词不得隐式调用，不进入通用类型 Skill。
- 若未来产品允许合规成人创作，必须单独设计年龄门槛、明确同意、内容政策、显式启用、审计记录和平台限制；在此之前保持隔离。
- 第三方小说抓取/解密 API、硬编码内网地址、ADB 手机提交和未授权仿写流程不得复用。

素材库未发现统一许可证，任何文字内容只作为内部方法研究；正式 Skill 使用重新抽象的原创规则，不复制长段内容。

## 5. `/Users/quchenchen/Documents/github/MuMuAINovel/backend/app/skills` 成熟度审计

该目录包含长篇/短篇写作、分析、市场扫描与文本去模板化等 7 组 Skill。它比普通提示词合集更接近工作流，但参考材料约 3.9 万行，且 loader 会把某个 Skill 的全部 references 一次性拼入 prompt；这会造成上下文膨胀、规则互相覆盖和模型注意力稀释，不能直接迁入 V7。

### A 级：机制成熟，优先吸收

- `story-long-analyze`：按章节切分、分批抽取、跨批聚合、矛盾检查和断点续作形成了完整的长篇分析管线。V7 应将其改造为数据库中的 RAG Loop：证据片段、原子事实、跨章关系、冲突项、覆盖率和人工确认均成为版本化产物，而不是写入 `_progress.md`。
- `story-deslop`：先诊断再最小修改、保留作者意图与人物声音的原则成熟。吸收为“文本肌理修复”，不使用全局禁词表，也不把口语化、短句化或粗糙化等同于人类感。
- `story-long-scan` / `story-short-scan` 的信息优先级：实时检索、用户资料、历史知识并明确时效，是正确的证据策略。它应成为独立市场研究能力，使用 MCP/Web、来源时间与引用，不隐式挂载到正文生成。

### B 级：素材丰富，需拆分重构

- `story-long-write`：人物、世界、长线期待、微创新和质量检查覆盖较全，但 references 过大且重复。按核心、平台、类型、质量四层渐进披露，不建立单一巨型 Skill。
- `story-short-write` / `story-short-analyze`：短篇需要更紧的情绪目标、因果链和伏笔回收，这一领域边界成立；固定反转数、篇幅比例和冲突间隔只保留为可配置诊断启发。
- `quality-checklist`：章节状态变化、目标—阻力—变化、连续性和避免总结式结尾等检查可进入质量层；精确对白比例、固定情绪强度和“每 N 字必须冲突”等规则不设为门禁。
- `style-modules`：可以作为类型与叙事策略的原始索引，但必须去重、按需读取并转写为可组合的小型参考，不允许一次性加载。

### C 级：不得固化为产品真理

- 平台字数、榜单规律、收益与更新频率等易变信息。
- “黄金开头”“固定反转”“固定对白占比”“每 300 字制造冲突”等无上下文公式。
- 以文件名关键词推断 Skill 分类、修改 Skill 后重启服务、将目录树当作作品状态的工程耦合。
- 无来源的市场数字、平台偏好和时效性结论。

### 对 V7 的架构约束

1. 使用 Skill 元数据表达角色、阶段、语言、平台、类型和能力，不根据名称猜测分类。
2. references 采用渐进披露；Resolver 先选 Skill，Agent 再按任务读取必要参考，禁止自动拼接全部材料。
3. 长篇分析保存 run checkpoint、证据引用、置信度、覆盖率和冲突状态；恢复运行不能依赖本地进度文件。
4. 数值规则必须标记为项目/平台可配置的 heuristic，不能成为跨类型的硬校验。
5. 市场扫描与创作执行解耦。只有用户显式要求或工作流进入市场研究阶段时，才允许调用具备来源追踪的 MCP/Web 工具。
6. 作品蒸馏只输出结构机制、人物关系、节奏特征和可解释风格画像，不复制参考文本的独特表达，也不生成作者仿写 Skill。

## 6. Skill 准入标准

一个候选 Skill 只有同时满足以下条件才可进入运行时：

1. 有清晰的触发描述，能判断何时使用和何时不使用。
2. 有明确角色、阶段、语言、平台/类型元数据。
3. 操作步骤可执行，输出与 V7 契约对应，不假设本地文件树。
4. 与核心、平台、类型、质量层的职责不重叠。
5. 有失败模式、组合边界、版权和内容安全约束。
6. 至少通过一个正向选择、一个反向排除和一个真实创作回归用例。
7. 修改形成新 digest；运行记录保存实际选中版本，允许回溯。

准入已由 `backend/skills/admission.json` 机器化：每个条件型小说 Skill 必须处于 `admitted`，绑定同一评测基线，并声明正向、反向与创作回归三类用例。测试会为每个已准入 Skill 根据其真实元数据执行一次正向 Resolver 路由、一次错误语言或错误阶段排除，并检查描述、步骤体量和渐进披露参考等回归契约。Resolver 和最终 AgentScope loader 双重拒绝未准入 Skill；仅把文件放入目录不会获得运行资格。管理后台同步展示“已准入/孵化中”和评测数量，避免把“能被发现”误认为“已可用于创作”。

## 7. 后续迭代

- 为新建项目增加显式目标平台字段，并在管理后台展示 Resolver 的选择理由。
- 将已建立的 `novel-source-distiller` 接入创作端的来源画像审核界面；RAG Loop 生成的候选画像仍须人工批准后才进入上下文。
- 建立类型组合冲突表，例如 romance + mystery 可以叠加，两个主导平台不能同时隐式选中。
- 用中文番茄都市/玄幻/言情/悬疑各一例，英文 romance/paranormal/speculative/thriller 各一例做端到端回归。
- 将作品质量反馈沉淀为项目专属 profile，不能直接污染全局 Skill；跨项目晋升需要聚合证据与人工审批。
- `novel-source-distiller` 采用“切分检索 → 原子证据 → 跨章聚合 → 矛盾/缺口 → 候选创作画像 → 人工批准”的多轮机制，并支持断点恢复。
- 后续独立评估 `novel-market-scan` 与 `novel-short-serial-strategy`；前者必须有联网证据，后者不能与长篇写作共享固定节奏公式。

## 8. 明确不做

- 本轮不建设剧本 Skill，不共享小说正文、StoryMap、Writer、审读或导出逻辑。
- 不把热门榜单当创作真理，不用单一“爆款公式”覆盖人物真实性。
- 不以作者姓名作为风格目标，不复制参考作品的独特表达或情节组合。

## 9. 2026-07-22 实施与回归证据

本轮已把“规划中的作品蒸馏”推进为可执行闭环：

- `SourceDistillationService` 保存六阶段检查点、原子证据、覆盖率、冲突、排除项与版本化候选画像。
- `SourceDistillationRunner` 按有限批次处理来源片段，分层聚合证据；任何模型输出引用未知 chunk/evidence key 都会拒绝入库。
- 断点恢复覆盖原子证据和跨章节综合两层：每个综合批次完成后保存 `synthesis_groups_processed`，Provider 在中途失败时只重跑未完成批次，不重复消费前序模型调用。
- `AgentRuntimeDistillationAnalyzer` 只在 `source-analysis` 阶段显式挂载 `novel-source-distiller`，不会把全库 Skill 或未批准画像注入上下文。
- Agent 最终输入统一声明上下文优先级：服务端已采纳事实与最新有效人工修订 > 用户当前要求 > 项目边界 > 已批准来源画像 > Skill/工具建议；新增契约测试证明人工修订与已批准画像会同时进入输入，而未批准画像不会被装配。
- AgentScope ReAct 循环继续受最多 12 次迭代约束；统一 `AgentRuntime.generate` 另增加可配置墙钟超时（开发默认 600 秒，允许部署覆盖），章节、发散、蓝图、蒸馏、审读和 Dock 调用共享同一超时失败语义，避免 Provider 挂起无限占用运行。
- API 支持启动、后台执行、状态查询、运行事件与人工批准；执行结束停在 `source_profile_decision`，不自动成为创作事实。
- 创作端为小说改编项目提供独立“来源画像”审查区：先展示模型服务商、模型、素材范围和用途，用户逐次授权后才执行；候选画像展示引用证据，批准后才进入后续创作上下文。
- 外部处理采用显式同意契约 `source-processing-v1`；API 缺少同意返回 428，CLI 缺少 `--allow-external-processing` 直接拒绝运行，授权动作写入审计日志。
- CLI 支持使用新的 ProjectRun 从原检查点恢复；瞬时 Provider 失败不清除已经处理的来源片段。
- 小说域新增版本化章节成熟度契约 `novel-chapter-quality-v1`，逐项评估人物能动性、场景因果、关系推进、叙述声音、连续性、来源边界、章节推动力和语言质感。每项必须提供正文证据、诊断和修订动作；来源越界等阻断项不会被平均分掩盖。报告绑定具体正文 revision、来源画像版本和 Skill 计划指纹，人工修订后旧报告只能作为历史比较，不能冒充当前质量。
- 质量报告拥有小说域独立表、服务和章节 API，支持幂等保存与按章查看历史；公开 API 只允许请求服务端评测与读取历史，不接受客户端自行提交的“通过”报告。`NovelQualityEvaluator` 以 reviewer 角色显式挂载 `novel-review` 与 `novel-serial-quality-review`，只审读一个不可变 revision，同时按 StoryMap 顺序读取前置章节的最新有效修订（含人工修订），严格解析八轴 JSON；失败时不修改正文或旧报告。开发 mock 只产生“需人工复核”报告，不冒充真实质量通过。
- 创作端“审读”侧栏显示当前 revision 对应的成熟度报告、八轴证据与修订方向，并支持重新评测；人工另存修订后旧报告不会继续显示。报告不会直接改写或自动采纳正文。
- 未继续扩展现有共享 `review` 适配层。共享审读模块与“小说/剧本审读域隔离”基线的偏差已列为后续去污染项。
- 后端全量 pytest 回归通过；Ruff 全目录通过；开发数据库已升级到唯一 Alembic head。前端 16 个测试文件、36 项测试通过，创作端与管理端生产构建通过。边界测试已修正为检查相对领域模块，而不会把共享包名 `@scriptflow/shared` 误判成 Script 领域依赖。

《月蚀之契》当前真实数据确认：1 个 ready DOCX 来源、142 个已索引 RAG 片段。真实运行已完成 inventory 并进入 `atomic_evidence`，检查点为 0/142；模型调用因执行环境不允许把上传手稿发送到外部 DashScope 而停止。对应 ProjectRun 已标记失败，蒸馏 run 保持可恢复。该结果证明本地状态机、租户范围、Skill 路由和恢复边界有效，但**不能**作为真实模型输出质量通过的证据。

同一真实项目另完成一次不联网的契约级 E2E（distillation `293255c4-c271-4b88-9fda-bc4eac2a61f2`）：142/142 真实索引片段全部经过 20 片段批处理，形成 142 条原子标记和 2 条综合标记；最终状态为 `human_decision / ready_with_gaps`，综合检查点 `[0,1]` 在终态仍可审计。验证候选 `1e836d42-a6e5-48d8-a518-651b01851835` 已明确驳回，项目既有批准画像保持不变。该证据证明真实数据库与完整状态机闭环，但本地 analyzer 刻意不做创作判断，因此仍不代表作品蒸馏质量通过。

新增只读完成度验收器 `python -m scriptflow_v7.novel.completion_audit <project-id>`。它不会以测试数量替代真实证据，而是逐项检查 Skill 准入、来源索引、本地 RAG Loop、真实模型蒸馏、批准画像、第一章当前有效修订、绑定批准画像的质量报告和缺陷回灌。对《月蚀之契》当前运行结果为 `incomplete`：Skill 准入（17 项）、来源索引（1 个 ready 文件、142 片段）、两次契约 RAG Loop、第一章有效人工修订（revision 2，16,771 字符）通过；真实模型蒸馏、批准画像、第一章真实质量报告和缺陷回灌尚未通过。

浏览器视觉验收未计入通过证据：内置浏览器安全策略拒绝控制本地地址；当前结论来自 API、组件测试和生产构建，仍需在可访问的本地浏览器中人工观察授权卡、进度、候选证据与审批状态。

仍需完成的验收：

1. 在用户明确授权来源手稿发送至所配置的第三方 Provider 后，从现有检查点完成 142 片段真实蒸馏。
2. 人工审查候选画像的证据覆盖、版权边界和创作价值，再批准或驳回。
3. 用批准画像重新生成《月蚀之契》第一章候选，核查引用、上下文优先级、声音、人物能动性与后续章节连续性。
4. 对第一章当前有效修订生成质量报告；修订后再次评测，确认缺陷收敛且报告绑定的新 revision 生效。
5. 将真实缺陷回灌 Skill 准入评测集；在此之前不得宣称《月蚀之契》端到端创作回归完成。
