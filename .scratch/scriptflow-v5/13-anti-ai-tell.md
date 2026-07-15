# 13 · 拒绝 AI 味：Skill few-shot 强化 + 检测器

- **Status**: proposed
- **Type**: feature
- **Blocked by**: 05
- **Blocks**: —
- **Est**: M
- **Parent PRD**: docs/PRD-V5.md §User Stories #36, #37, #38

## What to build

**Skill 强化：**
- 重写 `backend/app/skills/writing/main.md`：
  - 明确剧本纸格式（对齐 issue #12 的 format_checker）
  - 加至少 3 个高质量 few-shot 样例（人工挑选的短剧片段，标注 好/坏 对比）
  - 加"AI 味 anti-pattern" 明示（"避免：满篇 …… / 排比句 / 心理独白过多 / 过度总结" 等）
- `backend/app/skills/ideation/main.md`、`structure/main.md`、`review/main.md` 同样加 few-shot
- 建 `backend/app/skills/_style_refs/`：作为共享 few-shot 库，各 skill 通过 include 引用

**AI 味检测器：**
- `backend/app/services/ai_tell_detector.py`：
  - 词频黑名单（"竟然、然而、突然、终于、其实、原来、居然、反正、不禁" 高频出现 → 提示"AI 味")
  - 短句/长句比（AI 生成偏均匀，好剧本节奏参差 → 报"节奏太齐"）
  - LLM 判官（可选，用小 model 快审 → 输出 0-100 分）
  - 每篇输出 `{score, issues[{type, count, examples}]}`
- 集成到 Ralph Loop：detector 输出的 issues 合并进 review_issues 里，触发 Revise

**Style Reference (User Story #38 P1)：** 本 slice 只放接口，不做 UI。API 端点 `POST /api/projects/{pid}/style-ref` 上传 → 存作为 skill prompt 附加 context。

## Acceptance criteria

- [ ] Skill 文件重写并加 few-shot（Writing / Ideation / Structure / Review 4 个 skill）
- [ ] `ai_tell_detector.detect(text)` 返回结构化结果
- [ ] 一段有明显 AI 味的样本 → detector 得分 <60 且列出至少 3 个 issue
- [ ] 一段人写短剧样本 → detector 得分 >75
- [ ] 集成到 Ralph Loop：Writing 完成 → detector 跑 → 若得分低触发 Revise
- [ ] `backend/tests/test_ai_tell_detector.py` 用 fixture 覆盖 5+ 样本

## Notes

- Few-shot 样例质量决定一切 —— 需要 Q老师提供或授权 AI 从公开优秀剧本挑选片段
- 词频黑名单需要迭代（先给一版初始，运营中调）
- LLM 判官用 dashscope 便宜 model（qwen3.7-plus 之类）
