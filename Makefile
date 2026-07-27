.PHONY: help setup dev backend creator admin test test-backend test-frontend lint lint-backend lint-frontend build clean

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

docker-build:  ## 构建生产镜像
	docker build -t scriptnow:latest $(APP_DIR)

verify: test lint build  ## 全量验证（测试+静态+构建）

docker-up:  ## 启动生产容器 (端口 8080)
	docker compose -f $(APP_DIR)/docker-compose.yml up -d

docker-down:  ## 停止生产容器
	docker compose -f $(APP_DIR)/docker-compose.yml down

docker-dev:  ## 启动开发容器（热重载，三个服务）
	docker compose -f $(APP_DIR)/docker-compose.yml --profile dev up

docker-push:  ## 构建并推送镜像到 GitHub Container Registry
	docker build -t ghcr.io/quchenchen/scriptnow:latest $(APP_DIR)
	docker push ghcr.io/quchenchen/scriptnow:latest
