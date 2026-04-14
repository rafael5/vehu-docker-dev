# =============================================================================
# vista-fm-browser — VEHU development image
#
# Extends the YottaDB-maintained VEHU container (yottadb/octo-vehu) with:
#   - Python 3.12 (via uv)
#   - All project runtime + dev dependencies pre-installed into /opt/venv
#   - YottaDB Python connector (yottadb C extension)
#   - YottaDB environment auto-sourced in interactive shells
#
# Base image: yottadb/octo-vehu:latest-master
#   Rocky Linux 8, built nightly by YottaDB Inc. with the latest YottaDB,
#   Octo, and VEHU (VistA + synthetic patients).
#   Docker Hub: https://hub.docker.com/r/yottadb/octo-vehu
#
# Usage:
#   docker-compose up -d --build   # build + start (first run pulls base image)
#   docker-compose exec vehu bash  # open a dev shell
#
# Inside the container:
#   fm-browser files               # list all FileMan files
#   fm-browser serve               # web UI at http://localhost:5000
#   pytest tests/ -m integration   # integration tests against live YDB
# =============================================================================

FROM yottadb/octo-vehu:latest-master

# ---------------------------------------------------------------------------
# System build dependencies (Rocky Linux 8 — uses dnf)
# ---------------------------------------------------------------------------
# gcc + make are required to compile the yottadb Python C extension.
# The YottaDB C library is already in the base image.
RUN dnf install -y --nodocs \
        curl \
        gcc \
        make \
        git \
        vim-minimal \
        less \
        ranger \
        micro \
    && dnf clean all

# ---------------------------------------------------------------------------
# uv — manages Python 3.12 without touching system Python
# ---------------------------------------------------------------------------
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Install Python 3.12 into uv's managed toolchain
RUN uv python install 3.12

# ---------------------------------------------------------------------------
# Project venv at /opt/venv — intentionally OUTSIDE the source volume mount
# (/opt/vista-fm-browser is bind-mounted, /opt/venv survives that mount)
# ---------------------------------------------------------------------------
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

RUN uv venv --python 3.12 "${VIRTUAL_ENV}"

# ---------------------------------------------------------------------------
# yottadb Python connector
#
# Needs: YottaDB C library (present in base image)
#        YDB env vars (set at runtime via source /usr/local/etc/ydb_env_set)
# uv pip install targets the active VIRTUAL_ENV automatically.
# ---------------------------------------------------------------------------
RUN uv pip install --quiet yottadb \
    || echo "WARNING: yottadb connector install failed — retry after sourcing ydb env"

# ---------------------------------------------------------------------------
# Project runtime + dev dependencies
#
# We copy only the dependency manifests (not the source) so this layer is
# cached unless pyproject.toml or uv.lock changes.
# The project package itself is installed at container start from the
# bind-mounted source.
# ---------------------------------------------------------------------------
WORKDIR /opt/vista-fm-browser
COPY pyproject.toml uv.lock ./

RUN uv pip install --quiet \
        "click>=8.0" \
        "rich>=13.0" \
        "flask>=3.0" \
        "pandas>=2.0" \
        "tabulate>=0.9" \
        "pytest>=8.0" \
        pytest-cov \
        pytest-watch \
        pytest-randomly \
        ruff \
        mypy \
        pre-commit \
    && echo "Python deps installed"

# ---------------------------------------------------------------------------
# Shell environment: YottaDB + venv activated in every interactive session
#
# Rocky Linux uses /etc/bashrc (not /etc/bash.bashrc).
# YottaDB env is at /usr/local/etc/ydb_env_set in the yottadb/* images.
# ---------------------------------------------------------------------------
RUN printf '\n# --- vista-fm-browser dev environment ---\n' >> /etc/bashrc \
    && printf 'if [ -f /usr/local/etc/ydb_env_set ]; then\n' >> /etc/bashrc \
    && printf '  source /usr/local/etc/ydb_env_set\n' >> /etc/bashrc \
    && printf 'elif [ -f /etc/yottadb/env ]; then\n' >> /etc/bashrc \
    && printf '  source /etc/yottadb/env\n' >> /etc/bashrc \
    && printf 'fi\n' >> /etc/bashrc \
    && printf 'export VIRTUAL_ENV=/opt/venv\n' >> /etc/bashrc \
    && printf 'export PATH=/opt/venv/bin:$PATH\n' >> /etc/bashrc \
    && printf 'cd /opt/vista-fm-browser 2>/dev/null || true\n' >> /etc/bashrc

# ---------------------------------------------------------------------------
# Expose Flask web UI port
# ---------------------------------------------------------------------------
EXPOSE 5000
