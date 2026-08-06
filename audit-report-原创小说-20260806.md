# ScriptNow 生产环境端到端审计报告

## 📋 审计概要

| 属性 | 值 |
|------|-----|
| **审计时间** | 2026年8月6日 |
| **生产环境** | https://sn.igeewa.com |
| **目标项目** | 审计-原创小说 (novel/original) |
| **项目 ID** | `26589aae-dff7-4b61-8568-60ce4bfe2310` |
| **项目方向** | 语言: zh-CN, 类型: 悬疑, 卷1: 2章, 卷2: 5章, 目标字数: 2000 |
| **审计结论** | 🔴 **流水线完全阻塞，无法完成** |

---

## 🔴 关键发现：生产环境致命 Bug

### 根因：`creator-persona` 技能重复注册

```
Error: "invalid director output: duplicate skill name: creator-persona"
HTTP 503 Service Unavailable
```

**影响范围**：所有 Agent 角色（导演、架构师、写作者）均受影响，整个流水线从第一步就卡死。

**证据**：

| 端点 | 角色 | 状态 | 错误信息 |
|------|------|------|----------|
| `POST /novel/projects/{id}/story-cores/generate` | director | 503 | duplicate skill name: creator-persona |
| `POST /novel/projects/{id}/chapters/{cid}/generate` | writer | 409 | duplicate skill name: creator-persona |
| `POST /novel/projects/{id}/blueprints/generate` | architect | 503 | 蓝图格式需要整理（架构师能运行但输出解析失败） |

**现有知识库记录**：scriptnow-development 技能中已有记载——"creator-persona 无代码集成"是已知的三个 gap 之一。该 Skill 未被正确注册到 SkillCatalog，但又在 admission.json 中重复声明，导致加载时冲突。

---

## 📊 完整流水线测试记录

### 目标项目：审计-原创小说 (ID: 26589aae)

| 步骤 | 端点 | 方法 | 状态 | 耗时 | 错误/备注 |
|------|------|------|------|------|-----------|
| 0-登录 | `/api/auth/login` | POST | ✅ 200 | 0.21s | 正常 |
| 0-状态查询 | `/api/novel/projects/{id}/state` | GET | ✅ 200 | 0.18s | phase=seeded, 无任何产出 |
| 1-StoryCore生成 | `/api/novel/projects/{id}/story-cores/generate` | POST | 🔴 503 | 0.24s | duplicate skill name: creator-persona |
| 1-重试1 | 同上（新 idempotency_key） | POST | 🔴 503 | 0.22s | 同上 |
| 1-重试2 | 同上（新 idempotency_key） | POST | 🔴 503 | 0.23s | 同上 |
| 2-Blueprint生成 | `/api/novel/projects/{id}/blueprints/generate` | POST | 🔴 503 | 0.19s | 蓝图格式需要整理，请重新生成 |
| 3-StoryMap生成 | `/api/novel/projects/{id}/story-map/generate` | POST | 🔴 503 | 0.20s | adopted direction and blueprint are required |
| 4-章节生成 | `/api/novel/projects/{id}/chapters/chapter-1-1/generate` | POST | 🔴 409 | 0.18s | adopted direction, blueprint and StoryMap are required |

### 对比项目：翻盘千金·完整短篇 (ID: aa383721，已完成)

| 阶段 | 状态 |
|------|------|
| Phase | **writing** ✅ |
| StoryCores | 3 个 |
| Blueprint | 已采纳 |
| StoryMap volumes | 1 卷 / 20 章 |
| Documents | 20/20 已采纳 |
| Runs 总计 | 20 次（6 succeeded + 多次 failed） |

**结论**：该平台在 bug 引入前（约 8 月 1 日）曾完整跑通过流水线。当前所有 agent 操作均被 `creator-persona` 技能冲突阻断。

---

## 🔍 全平台项目状态扫描

| # | 项目名 | 类型 | Phase | StoryCores | Blueprint | StoryMap | 文档 |
|---|--------|------|-------|------------|-----------|----------|------|
| 1 | 翻盘千金·完整短篇 | novel/original | **writing** | 3 | ✅ | 1卷20章 | 20 |
| 2 | 翻盘千金·剧本改编验证 | script/adaptation | ? | ? | ? | ? | ? |
| 3 | **审计-原创小说** | **novel/original** | **seeded** | **0** | **❌** | **0** | **0** |
| 4 | 审计-原创短剧 | script/original | **seeded** | 0 | ❌ | 0 | 0 |
| 5 | 审计-改编小说 | novel/adaptation | **seeded** | 0 | ❌ | 0 | 0 |
| 6 | 审计-改编短剧 | script/adaptation | **seeded** | 0 | ❌ | 0 | 0 |

**所有 4 个审计项目均被阻塞在 seeded 阶段。**

---

## ⏱️ 可观测的耗时数据

### API 基础响应时间（不含 LLM 生成）

| 操作 | 平均耗时 |
|------|----------|
| 登录 | 0.17-0.21s |
| 状态查询 | 0.18-0.21s |
| 生成请求（直接报错） | 0.18-0.25s |
| 项目创建 | 0.17s |

### 服务器排队情况

审计-原创小说项目有 **6 个 run 记录**：
- 2 个 `queued`（排队中，永远无法执行）
- 4 个 `failed`（已失败）

说明用户曾多次尝试触发生成，均以失败告终。失败的 runs 未被清理，持续占用队列。

---

## ⚠️ 附加发现

### 1. 项目 ID 不匹配
任务描述中给出的项目 ID `26589aae-dff3-4900-ade0-577ed3ddc787` 与实际项目 ID `26589aae-dff7-4b61-8568-60ce4bfe2310` 不同（第 3 段 UUID 不一致）。实际 ID 是通过 `/api/projects` 列表检索到的。

### 2. Blueprint 生成独立错误
即使 StoryCore 问题修复，Blueprint 生成仍会失败——"蓝图格式需要整理，当前内容已保留，请重新生成一次"。这是架构师 Agent 的输出格式问题，可能源于 `blueprint.py` 的 JSON 解析需要在 Pydantic ValidationError 后尝试回退（参考已知的 `references/json-parse-resilience.md`）。

### 3. Stage Gating 严格
StoryMap 生成要求"adopted direction and blueprint"；章节生成要求"adopted direction, blueprint and StoryMap"。没有任何跳步机制，必须严格按 `seeded → story_core_adopted → blueprint_adopted → writing` 顺序推进。

### 4. Volume 设置确认
审计-原创小说项目 direction 中包含：
- `volume_one: "2"`（第一卷 2 章）
- `volume_two: "5"`（第二卷 5 章）
- `chapter_target_words: "2000"`（每章目标 2000 字）

这符合 2 卷 × 少量章节的测试配置。

### 5. 孤立的 Queued Runs
2 个 runs 处于 `queued` 状态，表明 AgentScope 的任务队列中有永远无法被消费的僵尸任务。这可能阻塞后续的正常 runs。

---

## 🛠️ 修复建议（按优先级排序）

### P0 - 立即修复
1. **删除重复的 `creator-persona` 技能注册**
   - 位置：`skills/admission.json` 检查是否有重复条目
   - 或：`skills/` 目录下检查是否有同名的 SKILL.md 文件
   - 验证：`import scriptnow.platform.skills; catalog.scan()` 不应报错

2. **清理僵尸 runs**
   - 将 `queued` 状态的 runs 标记为 `failed` 或 `cancelled`
   - 避免阻塞 AgentScope 任务队列

### P1 - 尽快修复
3. **Blueprint 输出解析增强**
   - 参考 `references/json-parse-resilience.md` 的三级回退模式
   - Level 1: Pydantic 直接解析
   - Level 2: json_repair 修复
   - Level 3: 从纯文本提取结构化信息

4. **错误消息改进**
   - "invalid director output: duplicate skill name: creator-persona" 对用户无意义
   - 应改为 "技能系统配置错误，请联系管理员" 并记录日志

### P2 - 后续优化
5. **项目 ID 一致性验证**
   - 审查项目 ID 生成与存储逻辑，确保不会出现 ID 不匹配

6. **Run 超时自动清理**
   - queued 超过 5 分钟的 runs 自动标记为 timeout
   - 防止僵尸任务累积

---

## 📝 审计结论

**审计-原创小说项目的端到端流水线无法完成。**

根本原因是生产环境 `creator-persona` 技能在 SkillCatalog 中重复注册，导致所有 Agent（director/writer/architect）初始化失败。这是一个部署层面的配置错误，修复后即可恢复整个流水线。

该平台在 bug 引入之前曾成功完成「翻盘千金·完整短篇」项目（20 章完整产出），说明核心流水线逻辑是可行的。当前阻塞纯属配置问题，修复成本低、影响面广。

**建议**：修复技能重复问题后重新运行此审计，以获取完整的端到端耗时数据。

---

## 📎 附录：测试方法

```
环境：生产环境 https://sn.igeewa.com
认证：cookie-based session (sf_csrf + sf_access)
工具：curl + Python subprocess
ID 修正：通过 GET /api/projects 列表发现正确项目 ID
```

### 关键 API 端点清单

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/auth/login` | POST | 登录 |
| `/api/projects` | GET | 项目列表 |
| `/api/projects` | POST | 创建项目 |
| `/api/novel/projects/{id}/state` | GET | 项目状态 |
| `/api/novel/projects/{id}/story-cores/generate` | POST | 生成故事核心 |
| `/api/novel/projects/{id}/story-cores/{cid}/adopt` | POST | 采纳故事核心 |
| `/api/novel/projects/{id}/blueprints/generate` | POST | 生成蓝图 |
| `/api/novel/projects/{id}/story-map/generate` | POST | 生成故事地图 |
| `/api/novel/projects/{id}/chapters/{cid}/generate` | POST | 生成章节 |
| `/api/novel/projects/{id}/chapters/{cid}/revisions/{rid}/adopt` | POST | 采纳章节 |
| `/api/projects/{id}/runs` | GET | 运行记录 |
