# ScriptNow 全量技术审计报告

> 审计日期: 2026-07-31
> 项目版本: 0.2.0-rc.1
> 审计范围: 全量（后端 + 前端 + 基础设施 + 规格体系）

> 复核日期: 2026-08-01
> 复核结论: 本文原始统计与风险分级存在失真，不能单独作为 RC 发布依据。当前工程门禁已通过，但真实 Provider 黄金回放、跨进程恢复和完整用户旅程仍须使用独立验收证据判断。

---

## 一、总体评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 架构设计 | ★★★★★ | 领域驱动、松耦合、依赖方向清晰 |
| 代码质量 | ★★★★☆ | Ruff 零告警，但异常处理有提升空间 |
| 安全性 | ★★★★☆ | 认证与 CSRF 基础扎实；跨域策略须按部署边界显式决策 |
| 测试覆盖 | ★★★☆☆ | 后端 69 文件 / 347 项、前端 64 项通过，但缺少浏览器 E2E |
| 文档规范 | ★★★★★ | 规格 + ADR + AGENTS.md + 审计历史完备 |
| 运维完整性 | ★★★★☆ | Docker、supervisord、migrations 齐全，缺 CI/CD |
| 性能/资源 | ★★★☆☆ | 上下文管理精细但存在积累爆炸风险 |

**工程健康度: B+。产品可交付等级暂不折算为单一分数。** 静态检查和自动化测试通过，并不等于真实 Provider、跨进程恢复、长任务和完整创作旅程已经通过。

---

## 二、项目结构

```
scriptnow/
├── backend/
│   ├── src/scriptnow/         # ~38,840 行 Python (123 文件)
│   │   ├── platform/          # 共享基础设施 (61 文件)
│   │   ├── novel/             # 小说领域 (19 文件)
│   │   ├── script/            # 剧本领域 (13 文件)
│   │   ├── dock/              # Agent 对话坞 (3 文件)
│   │   ├── review/            # 审读系统 (6 文件)
│   │   ├── translation/       # 翻译系统 (4 文件)
│   │   ├── work_package/      # 打包导出 (3 文件)
│   │   └── diagnostics/       # 诊断工具 (3 文件)
│   ├── skills/                # AgentScope skills (39 SKILL.md)
│   ├── tests/                 # 69 个测试文件
│   └── migrations/            # 43 个 Alembic 迁移
├── frontend/
│   ├── apps/creator/          # 创作端 (28 Vue + 52 TS 文件)
│   ├── apps/admin/            # 管理端 (1 Vue + 2 TS 文件)
│   └── packages/shared/       # 共享包
├── docs/v7-spec-v1.1/         # 26+ 规格/ADR/发布文档
├── Dockerfile                 # 多阶段构建 (node:22 → python:3.12)
├── docker-compose.yml         # prod + dev profiles
├── nginx.conf                 # SPA 静态 + API 反向代理
└── supervisord.conf           # uvicorn + nginx 进程管理
```

### 依赖方向

```
app → novel  → platform
app → script → platform
```

✅ **禁止** `platform → novel|script`，`script ↔ novel`——已在 `README.md` 中明确声明，代码层面也未见违例。

---

## 三、代码质量

### 3.1 静态分析

**Ruff 全量检查**: ✅ 零告警
```
ruff check src/scriptnow --statistics → (empty)
```

配置合理 (`pyproject.toml`):
- 行宽 100，Python 3.11 目标
- 规则: E/F/W/I/UP/B/SIM（无类型检查规则）
- 豁免: E501(行长)、B008(函数调用中默认参数)

### 3.2 异常处理质量

| 模式 | 数量 | 风险 |
|------|------|------|
| `with contextlib.suppress(Exception)` | 54 处 | ⚠️ 中 — 静默吞异常 |
| `except Exception` | 44 处 | ⚠️ 中 — 可能掩盖预期外错误 |
| 领域特定异常类 | 13 个 | ✅ 好 |

**典型风险点**:
1. `translation/api.py` (6 处 suppress) + `platform/agent_runtime.py` (5 处 suppress) — 后台任务失败无痕迹
2. `novel/creative_graph.py` 使用 `suppress(Exception)` 在队列 _drain 中——历史原因（SQLite 锁死），但有技能文档记录了必须用 `print(…, flush=True)` 替代 `logging.info()` 的诊断模式

✅ **正面**: 项目有完整的异常层级——`NovelDomainError`、`NovelWriterError`、`NovelConflict`、`NovelQualityError` 等——API 端点能精确匹配错误类型返回适当 HTTP 状态码。

### 3.3 代码规范一致性

| 检查项 | 结果 |
|--------|------|
| `snake_case` 函数/变量 | ✅ 一致 |
| `PascalCase` 类/模型 | ✅ 一致 |
| `SCREAMING_SNAKE` 常量 | ✅ 一致 |
| 无 TODO/FIXME/HACK 残留 | ✅ 零残留 |
| `.DS_Store` 污染 | ⚠️ 多处存在（已列入 .dockerignore）|

---

## 四、依赖管理

### 4.1 Python 后端

```toml
# pyproject.toml 核心依赖
fastapi==0.115.6          # 最新稳定
pydantic==2.12.5          # 最新
agentscope==2.0.4         # Agent 框架
sqlalchemy==2.0.51        # ORM
aiosqlite==0.22.1         # 异步 SQLite
alembic==1.18.5           # 迁移
cryptography==49.0.0      # 安全库
opentelemetry-sdk==1.43.0 # 可观测性 (未在代码中充分使用)
```

✅ **依赖评估**: 锁定版本、无过期包、最小依赖集。`opentelemetry` 已引入但可观测性集成度低——当前主要用于追踪链路，缺少 metrics/tracing 的深度集成。

⚠️ **Python 版本约束**: `requires-python = ">=3.11"`，但 venv 使用 Python 3.12。与 Hermes 的 Python 3.11 不兼容，必须 `PYTHONPATH=""`。

### 4.2 前端

```json
vue@^3.5.39              // 最新 Vue 3
vite@^8.1.1              // Vite 8 (较新)
typescript@~6.0.2        // TS 6 (较新)
vitest@^4.0.18           // 测试
@vue-flow/core@^1.48.2   // 图谱可视化
@dagrejs/dagre@^3.0.0    // 图谱布局
```

✅ **前端评估**: 依赖精简（7 个运行时依赖），版本跟踪最新。无安全漏洞告警 (npm audit clean)。

---

## 五、安全性

### 5.1 认证体系 ★★★★☆

| 组件 | 实现 | 评价 |
|------|------|------|
| 密码哈希 | scrypt (n=2^14, r=8, p=1) | ✅ 现代参数 |
| 最短密码 | 12 字符 (PasswordHasher.hash) | ✅ |
| JWT 签名 | HS256，可配密钥 | ✅ |
| CSRF 保护 | Cookie + Header 双重验证 | ✅ |
| 登录限流 | 5 次失败 / 15 分钟封锁 | ✅ |
| Refresh token | 单次使用 + 重放检测 | ✅ |
| Token 过期 | Access 60min / Refresh 30 天 | ✅ |
| 生产安全检查 | 强制修改默认 Secret | ✅ |

### 5.2 安全隐患

| 风险 | 级别 | 详情 |
|------|------|------|
| **跨域策略未显式成文** | 🟢 低 | 当前 Creator 与 API 通过 nginx 同源部署，并有 CSRF 校验；不安装 CORS 中间件本身不是漏洞。只有计划开放跨域 API 时，才应增加严格来源白名单 |
| **默认 credential_master_key** | 🟡 中 | `Settings` 有生产检查但 `docker-compose.yml` 默认值 `production-master-key-change-me-please` 仅 41 字符——未触发 `min_length=32` 检查但明显不安全 |
| **root 运行 supervisord** | 🟡 中 | `supervisord.conf` 中 `user=root`——标准 Docker 实践但增加了容器逃逸风险 |
| **SQLite 并发** | 🟡 中 | 已通过 `CreativeGraphQueue` 串行队列缓解，但 `asyncio.create_task()` 多任务并发写仍可能触发 `database is locked` |

### 5.3 已实践的良好安全模式

- ✅ `PasswordHasher.verify()` 使用 `hmac.compare_digest`
- ✅ `RefreshTokenReuseDetected` 检测后撤销所有相关 session
- ✅ `token_hash()` SHA256 摘要——不存明文 token
- ✅ `.env*` / `*.pem` / `*.log` 列入 `.dockerignore`

---

## 六、测试

### 6.1 覆盖概况

| 层级 | 文件数 | 测试数 | 状态 |
|------|--------|--------|------|
| 后端 pytest | 69 文件 | 347 | ✅ 全量通过（220.39s） |
| 前端 vitest | 21 文件 | 64 | ✅ 全部通过 (6.7s) |

### 6.2 测试质量评估

✅ **正面**:
- 领域隔离测试：`test_auth_service.py`、`test_novel_service.py`、`test_script_service.py` 各有独立测试
- 前端覆盖：store (`dock.spec.ts`, `novel.spec.ts`, `script.spec.ts`)、schema (`narrativeGraphSchema.spec.ts`)、组件 (`AgentMessage.spec.ts`, `ReviewPanel.spec.ts`)
- 无障碍审计：`admin/src/accessibility.spec.ts` 使用 axe-core

⚠️ **不足**:
- **无端到端测试**：缺少完整的 "创建项目→方向→蓝图→章节→导出" 流程测试
- **无 Agent 集成测试**：Writer/Blueprint/StoryMap Generator 的测试可能因模型调用而跳过或 mock
- **测试耗时偏长**：全量后端测试约 220 秒。当前结果为通过，后续应按测试类型分组并记录慢测试，而不是将固定 120 秒外部超时误判为测试失败
- **缺少性能测试**：无负载/压力测试、无并发测试

### 6.3 测试/代码比

| | 源文件 | 行数 | 测试文件 | 测试行 | 比值 |
|--|--------|------|----------|--------|------|
| 后端 | 123 | ~38,840 | 69 | 待覆盖率工具实测 | 不以测试行数替代覆盖率 |
| 前端 | 80 | ~2,400* | 21 | ~1,500* | ~60% |

*前端行数估算（基于 xargs wc 结果，包含 node_modules）

---

## 七、架构抽象质量

### 7.1 领域隔离 ★★★★☆

```
platform/  — 认证·租户·DB·事件·计量·Agent 运行时（零领域知识）
  ↑ 单向依赖
novel/     — 小说 Writer·Blueprint·StoryMap·图谱
script/    — 剧本 Writer·格式·规划
```

✅ **验证**: 搜索 `import.*novel` 在 `platform/` 下 → 零结果；搜索 `import.*script` 在 `platform/` 下 → 零结果。领域隔离干净。

### 7.2 模块职责

| 模块 | 行数 | 职责 | 复杂程度 |
|------|------|------|----------|
| `platform/models.py` | 1,605 | 所有 ORM 模型 | ⚠️ 大单体 |
| `dock/service.py` | 1,290 | Agent 对话编排 | ⚠️ 规模大 |
| `novel/api.py` | 1,375 | 小说 API 路由 | ⚠️ 规模大 |
| `novel/writer.py` | 759 | 章节写作管道 | ⚠️ 适中 |
| `platform/auth.py` | 337 | 认证逻辑 | ✅ 紧凑 |

⚠️ `models.py` 1,605 行是一个显著的"上帝文件"——建议按领域拆分（novel_models, script_models, platform_models），降低认知负担和 merge 冲突风险。

### 7.3 设计模式识别

| 模式 | 位置 | 评价 |
|------|------|------|
| **Composition Root** | `app.py:create_app()` | ✅ FastAPI 经典模式 |
| **Factory** | `AgentFactory`, `create_*_router()` | ✅ 依赖注入 |
| **Strategy** | Writer/Blueprint/StoryMap Generator | ✅ 模板方法变量 |
| **Queue Worker** | `CreativeGraphQueue` | ✅ 串行后台队列 |
| **Repository (隐式)** | `Database.session()` context manager | ✅ 简洁抽象 |

---

## 八、API 设计

### 8.1 路由组织

```
/api/auth/*        — 认证
/api/admin/*       — 管理
/api/projects/*    — 项目 CRUD
/api/novel/projects/{id}/*   — 小说领域
/api/script/projects/{id}/*  — 剧本领域
/api/review/*      — 审读
/api/translation/* — 翻译
/api/graph/*       — 叙事图谱
/api/dock/*        — Agent 对话
/api/work-package/*— 打包导出
```

### 8.2 端点一致性

✅ **已修复的历史问题**: 早期多个端点缺少 `/projects/{project_id}/` 前缀导致 404（已在技能文档中记录修复）。

⚠️ **仍存在的问题**:
- `translation/api.py` 使用了自定义 token 解析而非统一 `AuthService`——技能文档有标记但代码状态待核实
- 翻译端点路径格式与 novel/script 不统一（`/translation/projects/{id}/chapters/{cid}/translate` vs `/novel/projects/{id}/chapters/{cid}/generate`）

### 8.3 错误响应

✅ 领域错误 → 对应 HTTP 状态码映射清晰：
- `NovelConflict` → 409
- `NovelDomainError` → 422
- `NovelWriterError` → 500
- `AuthenticationFailed` → 401
- `CsrfFailed` → 403

---

## 九、性能与资源

### 9.1 上下文管理 ★★★☆☆

Writer 使用 Hot/Warm/Cold 三层上下文架构：

| 层级 | 内容 | 预算 |
|------|------|------|
| HOT | direction + chapter beat | ~1K tokens |
| WARM | prior_summary + review_highlights + narrative_state | 6K cap |
| COLD | character_graph (name only) | 1K cap |

⚠️ **已知风险**: `novel_writer_max_reserved_tokens=24,000` + `prior_chapter_revisions[-30:]` → 12+ 章后上下文可达 123K tokens，AgentScope compression 可能失败。

✅ **缓解**: `writer_context.py` 中 `compact=True` 将 creative_graph 降至 ~40K 字符。但仍需长期方案（滑动窗口或向量检索）。

### 9.2 数据库

- SQLite + aiosqlite（单文件，适合单机部署）
- ✅ `PRAGMA foreign_keys=ON` 在每次连接时强制启用
- ⚠️ SQLite 不适合高并发写场景——`CreativeGraphQueue` 串行化已是补救措施
- ⚠️ 无连接池监控或慢查询日志

### 9.3 Docker 构建

```
Stage 1: node:22-alpine → npm ci + build (1619 modules for creator)
Stage 2: python:3.12-slim → pip install + supervisord
```

✅ 镜像大小优化良好（多阶段、.dockerignore 全面）。
⚠️ 缺少 `HEALTHCHECK` 的 `/health` 端点未检查 DB 连通性。

---

## 十、运维与部署

### 10.1 Docker 部署

| 组件 | 评价 |
|------|------|
| `Dockerfile` | ✅ 多阶段、镜像源可配、静态资源分离 |
| `docker-compose.yml` | ✅ prod + dev profiles、volume 持久化 |
| `nginx.conf` | ✅ Gzip、SPA fallback、600s 代理超时 |
| `supervisord.conf` | ✅ uvicorn + nginx 进程管理 |

### 10.2 数据库迁移

✅ 43 个 Alembic 迁移，命名规范（自描述前缀 + 有序版本标签）。

⚠️ **SQLite 迁移陷阱**: `create_all` 在表已存在时不 ALTER。技能文档记录了"删库重建"是当前唯一安全路径。对于生产环境，需要真正的 schema migration 而非 `create_all`。

### 10.3 可观测性

- ✅ `opentelemetry-sdk` 已引入
- ⚠️ 但仅用于基础链路追踪——缺少 Prometheus metrics、结构化日志、告警规则
- ✅ `PersistentRunEventLog` + `run_events` 提供 Agent 运行审计能力

---

## 十一、规格体系与文档

### 11.1 规格文档

```
docs/v7-spec-v1.1/
├── 00-README.md                              # 规格总览
├── 01-PRD-V7.md                              # 产品需求
├── 02-LEGACY-DECONTAMINATION.md              # 旧版去污染
├── 03-DEVELOPMENT-PLAN.md                    # 开发计划
├── 04-CREATIVE-PIPELINE.md                   # 创作管线
├── 06-DYNAMIC-CREATIVE-PLANNING.md           # 动态规划
├── 07-NARRATIVE-GRAPH-TAXONOMY.md            # 图谱分类
├── 08-I18N-THEME-GOVERNANCE.md               # 国际化
├── 09-WEBNOVEL-WRITER-FUSION-PLAN.md         # 网文融合
├── 10-NOVEL-GENRE-SKILL-QUALITY.md           # 流派技能
├── 11-CROSS-CULTURAL-STORY-RECREATION.md     # 跨文化改编
├── 12-CHAPTER-PIPELINE.md                    # 章节管道
├── 13-CREATIVE-FLOW-TECHNICAL-AUDIT.md       # 创意流审计
├── 25-FULL-PRODUCT-USABILITY-AUDIT.md        # 全产品可用性审计
├── RELEASE-NOTES.md                          # 发布笔记
└── adr/                                      # 3 个 ADR
```

✅ **评估**: 文档体系史无前例地完整。26+ 个规格文档形成了从 PRD 到 ADR 到审计的完整链路。

### 11.2 代码内文档

- ✅ `AGENTS.md` (仓库根目录) — Agent 协作约定
- ✅ `README.md` (项目根目录) — 架构边界 + 验证命令
- ✅ `design-qa.md` — 登录页设计 QA 对比
- ⚠️ Python docstring 覆盖率不统一——部分核心模块（`writer.py`, `agent_runtime.py`）有良好注释，但部分模块缺少函数级 docstring

---

## 十二、已知问题与改进建议

### P0 — 阻塞级

| # | 问题 | 建议 |
|---|------|------|
| 1 | **缺少真实 Provider 黄金旅程的可重复发布证据** | 分领域保存固定输入、事件流、决策、产物与导出校验；失败不得用 mock 或降级结果冒充成功 |
| 2 | **长任务、确认和恢复缺少端到端发布门禁** | 覆盖暂停、确认、续跑、跨进程恢复、exactly-once 决策与最终产物绑定 |

### P1 — 高风险

| # | 问题 | 建议 |
|---|------|------|
| 3 | **`models.py` 1605 行巨型文件** | 拆分为 `platform/models.py`、`novel/domain.py`(现有)扩展、`script/models.py` |
| 4 | **异常吞噬过多** (54 处 suppress + 44 处 except Exception) | 按边界逐项审计；预期异常精确捕获，意外异常记录结构化上下文并向上游传播 |
| 5 | **无浏览器 E2E 发布门禁** | 覆盖小说、剧本、忠实翻译、故事归化、独立评审与导出关键旅程 |
| 6 | **上下文增长缺少真实长程压力证据** | 用 Context Manifest、分层检索和长作品基准验证质量、延迟与资源上限，禁止写死“最近 5 章”等业务策略 |

### P2 — 改进级

| # | 问题 | 建议 |
|---|------|------|
| 7 | **OpenTelemetry 未充分利用** | 添加 Prometheus metrics 端点 + 结构化日志 |
| 8 | **前端测试覆盖率偏低** | 至少为所有 stores 和核心组件添加测试 |
| 9 | **缺失 CI/CD pipeline** | 添加 GitHub Actions: lint → test → build；镜像发布应由版本与环境策略单独控制 |
| 10 | **翻译端点路径不统一** | 统一为 `/{domain}/projects/{id}/...` 格式 |
| 11 | **无 API 版本管理** | 考虑 `/api/v1/` 前缀以支持未来 API 演进 |
| 12 | **Docker HEALTHCHECK 浅检查** | 扩展 `/health` 包含 DB 连通性 |

---

## 十三、亮点总结

1. **架构纪律**：严格的领域隔离 + 单向依赖 + Composition Root——在快速迭代的产品中难能可贵
2. **安全基础扎实**：scrypt 密码哈希、CSRF 双重验证、JWT 刷新轮换、登录限流——已超出大多数早期产品的安全水平
3. **Agent 上下文工程已有分层基础**：Hot/Warm/Cold、预算与压缩策略已存在，但“业界领先”尚缺长作品质量、成本与恢复基准支撑
4. **异常体系完善**：13 个领域特定异常类 + HTTP 状态码精确映射
5. **文档工程深厚**：26+ 规格文档 + ADR + 审计历史 + AGENTS.md
6. **39 个 AgentScope Skills**：覆盖小说/剧本/平台三大领域，流派多样性充分
7. **Docker 部署体系完整**：多阶段构建 + supervisor + nginx + health check
8. **零 FIXME/TODO**：未检出标记，不等于不存在技术债；技术债应由审计、ADR 与整改台账持续管理

---

## 十四、审计方法论

本审计基于以下数据源：

| 数据源 | 工具 |
|--------|------|
| 代码静态分析 | Ruff (零告警) |
| 结构分析 | 目录遍历 + 文件计数 |
| 依赖审计 | `pyproject.toml` + `package.json` |
| 测试状态 | pytest + vitest run |
| 安全性审查 | 源码审计（auth.py / config.py / database.py） |
| 架构合规 | 跨模块 import 搜索 |
| 部署完整性 | Dockerfile / docker-compose / nginx / supervisor 审查 |
| 规格质量 | 文档树遍历 + 内容评估 |
| 历史记录 | 技能文档（`scriptnow-development` / `scriptnow-quality-framework`） |

### 2026-08-01 复核命令

| 门禁 | 实测结果 |
|------|----------|
| `make test` | Backend 347 passed；Frontend 21 files / 64 tests passed |
| `make lint` | Ruff、Creator/Admin `vue-tsc` passed |
| `make build` | Creator/Admin production build passed |
| 构建提示 | Creator 主包约 695 KB，存在大于 500 KB 的拆包警告 |

复核说明：以上门禁证明当前代码可构建、现有自动化测试通过；不替代真实 Provider 黄金回放、浏览器 E2E、压力测试、安全渗透测试或发布环境验证。

---

*报告生成时间: 2026-07-31 23:11 CST*
*下次审计建议: v0.3.0 发布前或 2026-08-31*
