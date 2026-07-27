# 小说题材 Skills 与质量提升量化机制

| | |
|---|---|
| 状态 | 已进入研发基线 |
| 范围 | Novel 领域；不适用于 Script |
| 能力地图 | `backend/skills/benchmarks/novel-genre-capability-map-v1.json` |
| 基准套件 | `backend/skills/benchmarks/novel-genre-benchmark-v2.json` |

## 1. 决策

外部题材模板不是只能阅读后搁置的资料。它们提供题材覆盖、常见策略和失败模式的
重要证据。ScriptNow 将其转化为自有能力，但不复制原文、固定情节和许可证不兼容的实现。

转化后的生产能力分为四层：

1. **题材覆盖地图**：确认 37 类是否有明确的 canonical tag 和能力所有者；
2. **可组合 Skill**：描述题材承诺、场景问题、策略、边界与失败模式；
3. **项目参数**：篇幅、章节、节奏比例、平台策略和阻断阈值由前端、项目配置或 Agent
   交互形成，不写死在 Skill；
4. **质量证据**：同条件基线与候选运行的成对结果，证明质量收益和成本边界。

这不是 37 套固定剧情。一个项目可按 CreativeProfile 组合平台、题材、风格和质量 Skill，
已采纳事实与最新人工修订始终拥有更高优先级。

## 2. 当前覆盖架构

37 个外部分类被规范化到 37 个 canonical tag，并由以下能力包负责：

- 中文玄幻仙侠与升级；
- 中文言情关系；
- 中文悬疑生存；
- 中文都市能力；
- 中文历史、年代与社会叙事；
- 中文商业情绪与关系推进；
- 中文脑洞短篇与规则悬疑；
- 中文职业、竞技与直播叙事；
- 英文商业言情、超自然言情、悬疑惊悚与推想连载。

“负责”不等于完全成熟。覆盖地图解决的是遗漏与路由，质量基准才决定能力是否真的提升。

## 3. 九个质量锚点

| 锚点 | 核心问题 |
|---|---|
| 题材承诺 | 文本是否兑现该题材独特冲突和情绪回报 |
| 人物能动性 | 人物是否以判断、选择和代价推动事件 |
| 因果推进 | 场景变化是否产生可追溯的新局面 |
| 情绪递进 | 压力和关系是否升级而非机械重复 |
| 信息设计 | 信息差、揭示和误判是否服务人物因果 |
| 设定后果 | 世界规则是否真实改变资源和选择 |
| 叙述声音 | 语言、视角和文本肌理是否匹配项目 |
| 连续阅读动力 | 后续需要是否来自本章变化 |
| 原创与边界 | 是否吸收机制而未复制独特表达与组合 |

权重和门禁属于版本化基准套件，可调整、可审计，不是运行时业务常量。

## 4. 成对基准方法

每个 benchmark case 必须在相同 brief、模型、采样参数和上下文预算下运行两次：

- `baseline`：不加载候选题材 Skill；
- `candidate`：只增加待评估 Skill，其余条件一致。

每次结果记录锚点评分、文本证据、输入/输出 tokens、延迟和 blocking failure。报告计算：

- 加权基础分与候选分；
- 绝对提升值；
- 每个锚点的提升或退化；
- token 成本倍率；
- 阻断失败数；
- 未通过的质量门禁。

评测输入不完整、case 未成对、锚点缺失或分数越界时直接失败，不以普通文本猜测补齐。

## 5. 准入状态

路由与质量必须分开：

| 状态 | 含义 |
|---|---|
| `admission_status=admitted` | 标签、角色、阶段、语言及负向路由测试通过 |
| `quality_status=baseline_required` | 可进入开发验证，但尚无质量提升证据 |
| `quality_status=passed` | 指定 digest 通过版本化成对基准 |
| `quality_status=failed` | 存在低分、退化、成本或阻断门禁失败 |

后台不得再把路由 case 数量显示成“质量评测项”。没有 report 的 Skill 只能显示“质量待对标”。

## 6. 执行与复现

评测器位于 `scriptnow.platform.skill_benchmarks`。离线证据可通过：

```bash
cd scriptnow/backend
PYTHONPATH=src .venv/bin/python scripts/evaluate_skill_benchmark.py \
  --suite skills/benchmarks/novel-genre-benchmark-v2.json \
  --trials /path/to/paired-trials.json \
  --candidate-digest <skill-digest> \
  --output /path/to/report.json
```

报告必须绑定 Skill digest、suite version 和 evaluator 标识。Skill 文本或参考资源变化后，旧报告
失效，必须重新运行。

## 7. 后续验收

1. 为每个宽泛能力包补足题材特定 benchmark case；
2. 建立固定模型参数的基线样本，进行盲审与模型裁判校准；
3. 把通过的报告以不可变证据登记到 admission registry；
4. 在管理后台呈现覆盖率、提升值、退化维度和成本倍率；
5. 质量未通过的候选不得自动晋升为租户默认能力；
6. 用户明确偏好和项目实测反馈可形成新候选，但仍须重新对标。
