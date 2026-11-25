.PHONY: help install lint format typecheck test test-unit test-cov check-all api litellm client-dev client-build

help:
	@echo "ForgeAI Staff Engineering Makefile"
	@echo "  make install      - Sync Python & Node dependencies"
	@echo "  make lint         - Run ruff check + format check"
	@echo "  make format       - Auto-format Python code with ruff"
	@echo "  make typecheck    - Run mypy --strict on app/"
	@echo "  make test         - Run full pytest suite"
	@echo "  make test-unit    - Run fast unit tests only"
	@echo "  make test-cov     - Run pytest with >=85% coverage gate"
	@echo "  make check-all    - Run lint + typecheck + test-cov + client checks"
	@echo "  make litellm      - Start LiteLLM proxy gateway on :4000"
	@echo "  make api          - Start FastAPI backend on :8000"
	@echo "  make client-dev   - Start Next.js 16 frontend on :3000"

install:
	uv sync --all-extras
	cd client && pnpm install

lint:
	uv run ruff check --config ruff.toml app tests
	uv run ruff format --check --config ruff.toml app tests

format:
	uv run ruff check --fix --config ruff.toml app tests
	uv run ruff format --config ruff.toml app tests

typecheck:
	uv run mypy --config-file mypy.ini app

test:
	uv run pytest -c pytest.ini

test-unit:
	uv run pytest -c pytest.ini -m unit

test-cov:
	uv run pytest -c pytest.ini --cov=app --cov-report=term-missing --cov-fail-under=85

check-all: lint typecheck test-cov
	cd client && pnpm lint && pnpm tsc --noEmit && pnpm build

litellm:
	uv run litellm --config litellm_config.yaml --port 4000

api:
	uv run uvicorn app.presentation.main:create_app --factory --host 0.0.0.0 --port 8000 --reload

client-dev:
	cd client && pnpm dev

client-build:
	cd client && pnpm build

