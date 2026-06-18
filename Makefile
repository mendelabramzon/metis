# Metis developer commands. `make check` is the single gate run locally and in CI.
.PHONY: install format lint typecheck test boundaries check eval clean help

help:
	@echo "Targets:"
	@echo "  install     uv sync the workspace (all packages + services)"
	@echo "  format      auto-format and auto-fix with ruff"
	@echo "  lint        ruff lint + format check (no writes)"
	@echo "  typecheck   mypy --strict over all package/service source"
	@echo "  test        pytest from the repo root"
	@echo "  boundaries  enforce import-linter dependency contracts"
	@echo "  check       boundaries + lint + typecheck + test"
	@echo "  eval        replay the small golden workspace (Stage 13 regression gate)"

install:
	uv sync --all-packages

format:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy packages/*/src services/*/src eval/src

test:
	uv run pytest

boundaries:
	uv run lint-imports --config .importlinter

eval:
	uv run python -m metis_eval.ci.small_golden

check: boundaries lint typecheck test

clean:
	rm -rf .mypy_cache .ruff_cache .pytest_cache .coverage htmlcov coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
