# ScriptNow

**AI agent–powered creative production for novels, scripts, translation, and cross-cultural story recreation.**

[简体中文](#简体中文) · [English](#english) · [日本語](#日本語) · [한국어](#한국어)

Current version: **`0.2.0-rc.1`**

---

## 简体中文

ScriptNow 是由 AI Agent 创作团队驱动的故事生产平台，覆盖小说、剧本、忠实翻译和跨文化故事归化。创作者负责方向、修订与最终判断；Agent 团队负责创意发散、蓝图规划、逐章或逐场创作、审读和交付。

### 核心能力

- 小说与剧本采用独立领域模型、StoryMap、写作、审读及导出流程。
- 候选稿、人工修订、采纳正文和历史版本具有明确边界。
- 通过可追溯上下文检索、素材图谱和 Context Manifest 支持长程创作。
- 支持忠实翻译、术语治理，以及分阶段的跨文化故事归化。
- 基于 AgentScope 2.0 运行 Agent、工具调用、确认、暂停与恢复流程。
- 提供创作端与管理端，管理 Provider、模型、Skill、MCP、记忆和用量。

### 五分钟启动

```bash
make setup
make dev
```

开发地址：

- 创作端：<http://127.0.0.1:5174>
- 管理端：<http://127.0.0.1:5173>
- 后端 API：<http://127.0.0.1:8000>

也可以分别运行 `make backend`、`make creator` 或 `make admin`。

### 工程边界

```text
scriptnow/
├── backend/
│   ├── src/scriptnow/
│   │   ├── platform/       # 共享平台能力
│   │   ├── novel/          # 小说领域
│   │   ├── script/         # 剧本领域
│   │   └── translation/    # 翻译领域
│   └── skills/             # 运行时 Skill 资产
└── frontend/
    ├── apps/creator/       # 创作端
    ├── apps/admin/         # 管理端
    └── packages/shared/    # 无领域语义的共享基础
```

小说与剧本只共享 `platform`，不共享正文、StoryMap、Writer、审读、格式或导出领域模块。

### 规格与验证

- [v1.1 规格基线](./docs/v7-spec-v1.1/00-README.md)
- [产品与技术规格](./docs/v7-spec-v1.1/01-PRD-V7.md)
- [旧资源隔离规则](./docs/v7-spec-v1.1/02-LEGACY-DECONTAMINATION.md)
- [发布说明](./docs/v7-spec-v1.1/RELEASE-NOTES.md)
- [归档索引](./docs/archive/README.md)

```bash
make test
make lint
make build
```

---

## English

ScriptNow is an AI agent–powered story production platform for novels, scripts, faithful translation, and cross-cultural story recreation. Creators retain control over direction, revision, and final decisions, while an agent team supports ideation, blueprint planning, chapter or scene production, review, and delivery.

### Core capabilities

- Separate domain models, StoryMaps, writing, review, and export workflows for novels and scripts.
- Explicit boundaries between candidates, human revisions, adopted manuscripts, and version history.
- Traceable context retrieval, narrative graphs, and Context Manifests for long-form continuity.
- Faithful translation, terminology governance, and staged cross-cultural story recreation.
- AgentScope 2.0–based agent execution, tool calls, confirmations, pause, and recovery.
- Creator and admin applications for providers, models, skills, MCP, memory, and usage.

### Start in five minutes

```bash
make setup
make dev
```

Development endpoints:

- Creator: <http://127.0.0.1:5174>
- Admin: <http://127.0.0.1:5173>
- Backend API: <http://127.0.0.1:8000>

Run individual services with `make backend`, `make creator`, or `make admin`.

### Architecture boundary

```text
scriptnow/
├── backend/
│   ├── src/scriptnow/
│   │   ├── platform/       # Shared platform capabilities
│   │   ├── novel/          # Novel domain
│   │   ├── script/         # Script domain
│   │   └── translation/    # Translation domain
│   └── skills/             # Runtime skill assets
└── frontend/
    ├── apps/creator/       # Creator application
    ├── apps/admin/         # Admin application
    └── packages/shared/    # Domain-neutral shared foundations
```

Novel and Script share only `platform`. They do not share manuscript, StoryMap, Writer, review, formatting, or export domain modules.

### Specifications and verification

- [v1.1 specification baseline](./docs/v7-spec-v1.1/00-README.md)
- [Product and technical specification](./docs/v7-spec-v1.1/01-PRD-V7.md)
- [Legacy decontamination rules](./docs/v7-spec-v1.1/02-LEGACY-DECONTAMINATION.md)
- [Release notes](./docs/v7-spec-v1.1/RELEASE-NOTES.md)
- [Archive index](./docs/archive/README.md)

```bash
make test
make lint
make build
```

---

## 日本語

ScriptNow は、小説、脚本、忠実翻訳、異文化向けストーリー再創作に対応する、AI エージェント駆動型の物語制作プラットフォームです。作者は方向性、修正、最終判断を担い、エージェントチームはアイデア展開、設計、章・シーン単位の執筆、レビュー、納品を支援します。

### 主な機能

- 小説と脚本に、それぞれ独立したドメインモデル、StoryMap、執筆、レビュー、出力フローを提供。
- 候補稿、人による修正、採用済み本文、履歴バージョンを明確に分離。
- 追跡可能なコンテキスト検索、物語グラフ、Context Manifest による長編の整合性維持。
- 忠実翻訳、用語管理、段階的な異文化向けストーリー再創作。
- AgentScope 2.0 に基づくエージェント実行、ツール呼び出し、確認、一時停止、再開。
- Provider、モデル、Skill、MCP、メモリ、使用量を管理する制作画面と管理画面。

### 5 分で起動

```bash
make setup
make dev
```

開発用 URL：

- 制作画面：<http://127.0.0.1:5174>
- 管理画面：<http://127.0.0.1:5173>
- バックエンド API：<http://127.0.0.1:8000>

個別に起動する場合は、`make backend`、`make creator`、`make admin` を使用します。

### アーキテクチャ境界

```text
scriptnow/
├── backend/
│   ├── src/scriptnow/
│   │   ├── platform/       # 共通プラットフォーム機能
│   │   ├── novel/          # 小説ドメイン
│   │   ├── script/         # 脚本ドメイン
│   │   └── translation/    # 翻訳ドメイン
│   └── skills/             # 実行時 Skill
└── frontend/
    ├── apps/creator/       # 制作画面
    ├── apps/admin/         # 管理画面
    └── packages/shared/    # ドメイン非依存の共通基盤
```

小説と脚本が共有するのは `platform` のみです。本文、StoryMap、Writer、レビュー、書式、出力の各ドメインモジュールは共有しません。

### 仕様と検証

- [v1.1 仕様基準](./docs/v7-spec-v1.1/00-README.md)
- [製品・技術仕様](./docs/v7-spec-v1.1/01-PRD-V7.md)
- [旧資産の隔離ルール](./docs/v7-spec-v1.1/02-LEGACY-DECONTAMINATION.md)
- [リリースノート](./docs/v7-spec-v1.1/RELEASE-NOTES.md)
- [アーカイブ索引](./docs/archive/README.md)

```bash
make test
make lint
make build
```

---

## 한국어

ScriptNow는 소설, 대본, 충실 번역 및 문화권별 스토리 재창작을 지원하는 AI 에이전트 기반 스토리 제작 플랫폼입니다. 창작자는 방향, 수정, 최종 판단을 담당하고 에이전트 팀은 아이디어 확장, 청사진 설계, 장·장면 단위 집필, 검토 및 결과물 제작을 지원합니다.

### 핵심 기능

- 소설과 대본에 각각 독립된 도메인 모델, StoryMap, 집필, 검토 및 내보내기 흐름을 제공합니다.
- 후보 원고, 사용자 수정본, 채택된 본문 및 버전 기록의 경계를 명확히 구분합니다.
- 추적 가능한 컨텍스트 검색, 내러티브 그래프 및 Context Manifest로 장편의 연속성을 유지합니다.
- 충실 번역, 용어 관리 및 단계별 문화권 스토리 재창작을 지원합니다.
- AgentScope 2.0 기반 에이전트 실행, 도구 호출, 확인, 일시 정지 및 복구를 제공합니다.
- Provider, 모델, Skill, MCP, 메모리 및 사용량을 관리하는 창작 앱과 관리 앱을 제공합니다.

### 5분 안에 시작하기

```bash
make setup
make dev
```

개발 주소:

- 창작 앱: <http://127.0.0.1:5174>
- 관리 앱: <http://127.0.0.1:5173>
- 백엔드 API: <http://127.0.0.1:8000>

개별 서비스는 `make backend`, `make creator`, `make admin`으로 실행할 수 있습니다.

### 아키텍처 경계

```text
scriptnow/
├── backend/
│   ├── src/scriptnow/
│   │   ├── platform/       # 공통 플랫폼 기능
│   │   ├── novel/          # 소설 도메인
│   │   ├── script/         # 대본 도메인
│   │   └── translation/    # 번역 도메인
│   └── skills/             # 런타임 Skill 자산
└── frontend/
    ├── apps/creator/       # 창작 앱
    ├── apps/admin/         # 관리 앱
    └── packages/shared/    # 도메인 중립 공통 기반
```

소설과 대본은 `platform`만 공유합니다. 본문, StoryMap, Writer, 검토, 형식 및 내보내기 도메인 모듈은 공유하지 않습니다.

### 사양 및 검증

- [v1.1 사양 기준](./docs/v7-spec-v1.1/00-README.md)
- [제품 및 기술 사양](./docs/v7-spec-v1.1/01-PRD-V7.md)
- [레거시 격리 규칙](./docs/v7-spec-v1.1/02-LEGACY-DECONTAMINATION.md)
- [릴리스 노트](./docs/v7-spec-v1.1/RELEASE-NOTES.md)
- [아카이브 색인](./docs/archive/README.md)

```bash
make test
make lint
make build
```

---

## License

Proprietary. All rights reserved.
