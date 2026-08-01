.PHONY: help setup dev backend creator admin test test-backend test-frontend lint lint-backend lint-frontend build clean golden-contracts golden-audit-project

APP_DIR := scriptnow
BACKEND_DIR := $(APP_DIR)/backend
FRONTEND_DIR := $(APP_DIR)/frontend

help:  ## 显示帮助
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup:  ## 安装后端与前端依赖
	cd $(BACKEND_DIR) && uv sync --extra dev
	cd $(FRONTEND_DIR) && npm install

dev:  ## 同时启动后端、创作端与管理端
	@echo "后端 :8000 · 创作端 :5174 · 管理端 :5173"
	@cd $(BACKEND_DIR) && .venv/bin/alembic upgrade head
	@(cd $(BACKEND_DIR) && .venv/bin/python -m uvicorn scriptnow.app:app --reload --port 8000) & \
	 (cd $(FRONTEND_DIR) && npm run dev:creator) & \
	 (cd $(FRONTEND_DIR) && npm run dev:admin) & \
	 wait

backend:  ## 只启动后端
	cd $(BACKEND_DIR) && .venv/bin/alembic upgrade head
	cd $(BACKEND_DIR) && .venv/bin/python -m uvicorn scriptnow.app:app --reload --port 8000

creator:  ## 只启动创作端
	cd $(FRONTEND_DIR) && npm run dev:creator

admin:  ## 只启动管理端
	cd $(FRONTEND_DIR) && npm run dev:admin

test: test-backend test-frontend  ## 运行全部测试

test-backend:
	cd $(BACKEND_DIR) && .venv/bin/python -m pytest

test-frontend:
	cd $(FRONTEND_DIR) && npm test

golden-contracts:  ## 校验四领域黄金场景与统一完成定义
	cd $(BACKEND_DIR) && .venv/bin/python -m pytest \
		tests/test_creative_flow_audit.py \
		tests/test_creative_flow_evidence.py \
		tests/test_creative_flow_golden_replay.py

golden-audit-project:  ## 只读审计真实项目（SCENARIO=script-original PROJECT_ID=... OUTPUT_DIR=...）
	@test -n "$(SCENARIO)" || (echo "缺少 SCENARIO" && exit 2)
	@test -n "$(PROJECT_ID)" || (echo "缺少 PROJECT_ID" && exit 2)
	@test -n "$(OUTPUT_DIR)" || (echo "缺少 OUTPUT_DIR" && exit 2)
	mkdir -p "$(OUTPUT_DIR)"
	cd $(BACKEND_DIR) && .venv/bin/python scripts/collect_creative_flow_evidence.py \
		--scenario "golden/creative-flow-v1/$(SCENARIO).json" \
		--project-id "$(PROJECT_ID)" \
		--output "$(abspath $(OUTPUT_DIR))/$(SCENARIO)-observation.json"
	cd $(BACKEND_DIR) && .venv/bin/python scripts/audit_creative_flows.py \
		--scenario "golden/creative-flow-v1/$(SCENARIO).json" \
		--observation "$(abspath $(OUTPUT_DIR))/$(SCENARIO)-observation.json" \
		--output "$(abspath $(OUTPUT_DIR))/$(SCENARIO)-audit.json"

lint: lint-backend lint-frontend  ## 运行静态检查

lint-backend:
	cd $(BACKEND_DIR) && .venv/bin/python -m ruff check .

lint-frontend:
	cd $(FRONTEND_DIR) && npx vue-tsc -p apps/creator/tsconfig.json
	cd $(FRONTEND_DIR) && npx vue-tsc -p apps/admin/tsconfig.json

build:  ## 构建两个前端应用
	cd $(FRONTEND_DIR) && npm run build

clean:  ## 清理可重建缓存
	find $(APP_DIR) -type d -name __pycache__ -prune -exec rm -r {} + 2>/dev/null || true
	find $(APP_DIR) -type d -name .pytest_cache -prune -exec rm -r {} + 2>/dev/null || true
	find $(APP_DIR) -type d -name .ruff_cache -prune -exec rm -r {} + 2>/dev/null || true

# ── Docker ─────────────────────────────────────────────────────

DEPLOY_ENV ?= $(APP_DIR)/deploy.env
DOCKER_COMPOSE = docker compose --env-file $(DEPLOY_ENV) -f $(APP_DIR)/docker-compose.yml

docker-build:  ## 使用 deploy.env 构建生产镜像
	test -f $(DEPLOY_ENV) || (echo "Missing $(DEPLOY_ENV); copy $(APP_DIR)/deploy.env.example first" && exit 1)
	$(DOCKER_COMPOSE) build --pull

verify: test lint build  ## 全量验证（测试+静态+构建）

docker-up:  ## 使用 deploy.env 启动生产容器
	test -f $(DEPLOY_ENV) || (echo "Missing $(DEPLOY_ENV); copy $(APP_DIR)/deploy.env.example first" && exit 1)
	$(DOCKER_COMPOSE) up -d --remove-orphans

docker-down:  ## 停止生产容器
	test -f $(DEPLOY_ENV) || (echo "Missing $(DEPLOY_ENV); copy $(APP_DIR)/deploy.env.example first" && exit 1)
	$(DOCKER_COMPOSE) down

docker-dev:  ## 启动开发容器（热重载，三个服务）
	SCRIPTNOW_ACCESS_TOKEN_SECRET=development-compose-interpolation-only \
	SCRIPTNOW_CREDENTIAL_MASTER_KEY=development-compose-interpolation-only \
		docker compose -f $(APP_DIR)/docker-compose.yml --profile dev \
		up backend creator admin

docker-push:  ## 构建并推送镜像到 GitHub Container Registry
	docker build -t ghcr.io/quchenchen/scriptnow:latest $(APP_DIR)
	docker push ghcr.io/quchenchen/scriptnow:latest
