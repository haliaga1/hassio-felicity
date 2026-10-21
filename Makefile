.PHONY: help install sync lint format typecheck test test-all cov check clean build publish-dry

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install the dev environment
	uv sync --all-packages --all-extras

sync: install

lint: ## Run ruff lint + format check
	uv run ruff check .
	uv run ruff format --check .

format: ## Auto-format the code
	uv run ruff format .
	uv run ruff check --fix .

typecheck: ## Run mypy in strict mode
	uv run mypy

test: ## Run the unit + contract tests
	uv run pytest -m "not integration"

test-all: ## Run every test, including the ones that hit the real API
	uv run pytest

cov: ## Run the tests with a coverage report
	uv run pytest -m "not integration" --cov --cov-report=term-missing --cov-report=html

check: lint typecheck test ## Run the full local gate

clean: ## Remove build and cache artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

build: ## Build the wheel and sdist
	uv build packages/felicity-client

publish-dry: build ## Verify the package can be uploaded to PyPI
	uv run twine check dist/*
