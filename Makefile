.PHONY: install test test-lf watch lint format mypy cov check push pull hooks \
        build up down logs container-install

# On the host, tools live in .venv/.  Inside the container they are in
# /opt/venv (on PATH).  When inside the container, /opt/venv/bin/pytest etc.
# are available directly without the prefix — but the Makefile still works
# because the venv is on PATH via /etc/bash.bashrc.
PYTHON     := .venv/bin/python
PYTEST     := .venv/bin/pytest
RUFF       := .venv/bin/ruff
MYPY       := .venv/bin/mypy
PRECOMMIT  := .venv/bin/pre-commit
PTW        := .venv/bin/ptw

# Host: create .venv and install deps
install:
	uv sync --extra dev
	$(MAKE) hooks

# Container build / lifecycle (run from host)
build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f vehu

# Inside the container: install the project package (editable) into /opt/venv.
# Run once after `docker-compose up` or when switching branches.
container-install:
	/opt/venv/bin/pip install -e '.[dev]' -q

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
