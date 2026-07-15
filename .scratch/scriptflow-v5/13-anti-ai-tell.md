# 13 · 拒绝 AI 味：Skill anti-pattern 强化 + 检测器

- **Status**: done (detector + skill anti-pattern; few-shot 库留待 Q老师授权真剧本)
- **Type**: feature
- **Blocked by**: 05
- **Blocks**: —
- **Est**: M
- **Parent PRD**: docs/PRD-V5.md §User Stories #36, #37, #38

## What to build

### AI 味检测器 (done)

`app/services/ai_tell_detector.py` — 三个信号，纯函数不打 LLM：

1. **叙述连词密度** — 词频黑名单（竟然/然而/突然/终于/其实/原来 等 18 词）+ per-1000-char 阈值 + 3+ heavy words → severity=high
2. **内心独白标记** — 心想/暗想/内心/自言自语/暗自 等 8 标记，超阈值报 `inner_monologue_overuse`
3. **句长均匀度** — 分句后 CV (coefficient of variation)，< 0.5 就报 `sentence_rhythm_uniform`；< 0.3 为 high

清洗规则：分析前剥掉 `【场景N】` 头 + `△` 动作行，只对叙述+对白正文打分，避免误伤格式行。

Score 起始 100，high 扣 15、medium 扣 10、low 扣 5。

### Skill anti-pattern 强化 (done)

`app/skills/writing/main.md` 重写"⚠ 拒绝 AI 味"section，明示 6 类 anti-pattern：
- 叙述连词过密
- 内心独白泛滥
- 句长过于均匀
- 排比+三段式
- 总结性收尾
- 过度书面语

每类都有 bad/good 对比。示例框架保留，Few-shot 位子留 `app/skills/_style_refs/`（README 说明 Q老师授权真剧本后填入）。

### Ralph loop 集成 (done)

`ralph_service.run_iteration` 在 review agent 之后跑 detector：
- Detector issues 合并到 review issues
- 若 detector score < 60，overall_score 扣 `(60 - detector_score) * 0.5`

## Acceptance criteria

- [x] `ai_tell_detector.detect(text)` 返回 `{score, sentence_count, issues[]}` 结构化
- [x] 一段有明显 AI 味样本 → score < 80 且列出至少 3 类问题（`test_combined_ai_tell_deep_score_drop`）
- [x] 一段干净短剧样本 → score ≥ 80（`test_clean_drama_fragment_stays_high`）
- [x] 集成到 Ralph Loop：Writing 完成 → detector 跑 → 若 score < 60 拉低 overall_score
- [x] `test_ai_tell_detector.py` 用 fixture 覆盖 8 样本（empty / clean / 3 单类 issue / combined / scene-header 剥离 / issues_for_ralph shape / severity table）
- [x] `test_ralph_ai_tell_integration.py` 2 端到端（AI-tell episode 扣分 + 干净 episode 不扣分）
- [x] Skill anti-pattern 明示（Writing skill 完成；Review skill 因原 prompt 已经六维打分，未重写）
- [ ] Ideation / Structure skill anti-pattern — 保留待后续（当前 Writing 是最关键的产出环节）
- [ ] Few-shot 真剧本 —— `_style_refs/` 目录 + README 就位，等 Q老师提供或授权
- [ ] LLM 判官（可选）—— 未做，纯启发式够 tracer bullet
- [ ] Style Reference API 端点 —— 未做（依赖 few-shot 落地）

## Notes

- 检测器纯函数 = pytest 极快（0.09s / 11 tests）
- 词频黑名单是初版；实际运营中要按 corpus 迭代（Chinese short-drama specific）
- Detector 只对 Ralph loop 打分产生**影响性**（-5 到 -20 分），不作 hard veto
- Few-shot 真剧本是"质量决定一切"的部分，属 Q老师内容工作，agent 无法自行填
