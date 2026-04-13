.PHONY: install test test-lf watch lint format mypy cov check push pull hooks

PYTHON     := .venv/bin/python
PYTEST     := .venv/bin/pytest
RUFF       := .venv/bin/ruff
MYPY       := .venv/bin/mypy
PRECOMMIT  := .venv/bin/pre-commit
PTW        := .venv/bin/ptw

install:
	uv sync --extra dev
	$(MAKE) hooks

hooks:
	$(PRECOMMIT) install --hook-type pre-commit --hook-type pre-push

test:
	$(PYTEST)

test-lf:
	$(PYTEST) --lf

watch:
	$(PTW) -- --tb=short

lint:
	$(RUFF) check src/ tests/

format:
	$(RUFF) format src/ tests/

mypy:
	$(MYPY) src/

cov:
	$(PYTEST) --cov --cov-report=term-missing

check: lint mypy cov

pull:
	git pull origin main

push: check
	git push origin main
