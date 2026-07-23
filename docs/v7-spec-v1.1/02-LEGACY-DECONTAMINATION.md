# V7 Legacy Decontamination

## 目标

阻止旧领域语言、旧产品流程、重复原型、构建产物和未验证兼容代码污染 V7。清理不以“删得多”为目标，而以建立单一可信基线为目标。

## 分类规则

| 分类 | 条件 | 动作 |
|---|---|---|
| reuse | 语义与 V7 完全一致、公共接口稳定、测试覆盖 | 迁入 V7 正式模块并保留测试 |
| migrate | 核心实现可用但接口或数据契约不同 | 通过适配测试迁移；迁移完成后删除适配层 |
| isolate | 价值未确认或测试不足 | 留在 legacy 区；V7 禁止直接 import |
| archive | 仅有历史、研究或设计参考价值 | 移入 `docs/archive/pre-v7/` 并标记非开发依据 |
| delete | 可重建产物、重复文件、零引用死代码 | 确认引用后删除；以 Git 或备份恢复 |

## 复用门槛

1. 先写 characterization test，记录旧模块真实行为。
2. 对照 V7 契约，不按文件名或功能名称判断“看起来能复用”。
3. Script 与 Novel 的领域模块禁止互相 import；共享代码只能位于 platform 层。
4. 为复用引入长期兼容分支、旧字段别名或双写时，默认判定为不复用。
5. 每项迁移必须记录来源、目标、保留理由、删除条件和负责人。

## 首轮范围

### 平台层优先评估复用

- FastAPI 应用骨架与数据库访问模式
- AgentScope 2.0.4 封装经验
- JWT、安全工具和 ownership 测试思路
- 文件解析、分块、RAG 与流式传输基础设施
- DOCX 技术实现中的通用排版设施
- 前端 API 客户端、测试脚手架与设计 token

### 默认不直接复用

- Growth Tree、Living Assets、Ralph、Reflection、旧 pipeline 等 V5 领域实现
- 同时承载 Script/Novel 的旧 Writer、StoryMap 和正文模型
- 旧 Agent 名称、prompt、阶段门控和领域状态枚举
- 未经验证的模型路由、计费和 memory 双写逻辑

### 可直接删除的可重建产物

- `.pytest_cache/`、`.ruff_cache/`、`__pycache__/`
- `frontend/dist/`、`scriptflow-v6/frontend/dist/`
- 已可通过锁文件恢复的 `node_modules/`
- 空的误生成目录和确认无引用的临时文件

## 执行顺序

1. 建立 V7 新工程边界和 import 规则。
2. 生成全仓库引用图与资产清单。
3. 平台能力逐项做 characterization test。
4. 将确认复用的实现迁入 V7；禁止从 V7 直接引用 legacy 路径。
5. 历史文档归档，根入口只指向 v1.1。
6. 删除已迁移代码和可重建产物。
7. 运行引用扫描、后端测试、前端测试和双 SPA build。

## 删除检查表

- [ ] 目标路径明确且不包含仓库根、用户目录或未解析通配符
- [ ] Git 已跟踪，或存在独立备份，或属于可重建产物
- [ ] `rg` 未发现生产引用
- [ ] 替代实现及测试已存在
- [ ] 删除后测试和构建通过
- [ ] 清理记录列出删除内容与恢复方式
