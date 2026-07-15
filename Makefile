.PHONY: help setup dev backend frontend test test-backend test-frontend lint lint-backend lint-frontend clean

help:  ## 显示这份帮助
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup:  ## 首次装依赖（后端 + 前端）
	cd backend && python3.11 -m venv .venv || true
	cd backend && .venv/bin/pip install -e ".[dev]"
	cd frontend && npm install

dev:  ## 同时起后端 (:8000) 和前端 (:5173)
	@echo "启动后端 & 前端。用 Ctrl+C 停止两个。"
	@(cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000) & \
	 (cd frontend && npm run dev) & \
	 wait

backend:  ## 只起后端
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:  ## 只起前端
	cd frontend && npm run dev

test: test-backend test-frontend  ## 跑所有测试

test-backend:  ## 后端 pytest
	cd backend && .venv/bin/pytest

test-frontend:  ## 前端 vitest（issue #01 之后）
	@echo "前端测试骨架在 issue #01 里加"

lint: lint-backend lint-frontend  ## 跑所有 linter

lint-backend:  ## ruff 后端
	cd backend && .venv/bin/ruff check .

lint-frontend:  ## 前端 lint（暂用 tsc）
	cd frontend && npx vue-tsc --noEmit

clean:  ## 清 caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
