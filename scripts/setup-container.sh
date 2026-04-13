#!/usr/bin/env bash
# =============================================================================
# setup-container.sh
# Install all required tools inside the running VEHU container.
#
# Run from the host ONCE after first `docker-compose up`:
#   bash scripts/setup-container.sh
#
# Safe to run again (idempotent).
# =============================================================================

set -euo pipefail

CONTAINER=vehu
PROJECT_DIR=/opt/vista-fm-browser

echo "=== Setting up VEHU container for vista-fm-browser ==="
echo ""

# Verify container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  echo "ERROR: Container '${CONTAINER}' is not running."
  echo "Run: docker-compose up -d"
  exit 1
fi

run() {
  echo "  + $*"
  docker exec "$CONTAINER" bash -c "$*"
}

echo "--- System packages ---"
run "apt-get update -qq"
run "apt-get install -y -qq python3 python3-pip python3-venv python3-dev \
    gcc make curl git vim less 2>/dev/null || true"

echo ""
echo "--- YottaDB Python connector ---"
# The yottadb package requires the YottaDB C library (already in the container)
# and the yottadb environment variables to be set.
run "pip3 install --quiet yottadb 2>/dev/null || \
     pip3 install --quiet yottadb --break-system-packages"

echo ""
echo "--- Project Python dependencies ---"
run "pip3 install --quiet -e '${PROJECT_DIR}[dev]' --break-system-packages 2>/dev/null || \
     pip3 install --quiet -e '${PROJECT_DIR}[dev]'"

echo ""
echo "--- Verify yottadb connector ---"
docker exec "$CONTAINER" bash -c "
  source /etc/yottadb/env 2>/dev/null || true
  python3 -c 'import yottadb; print(\"yottadb connector: OK\")' 2>/dev/null || \
  echo 'WARN: yottadb import failed — check YDB env vars inside container'
"

echo ""
echo "--- Verify fm-browser CLI ---"
docker exec "$CONTAINER" bash -c "
  cd ${PROJECT_DIR}
  python3 -c 'from vista_fm_browser.data_dictionary import DataDictionary; print(\"vista_fm_browser: OK\")'
"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Open ${PROJECT_DIR} in VSCode"
echo "  2. 'Reopen in Container' (uses .devcontainer/devcontainer.json)"
echo "  3. Inside the container terminal:"
echo "       source /etc/yottadb/env   # activate YottaDB env vars"
echo "       fm-browser files           # browse FileMan files"
echo "       fm-browser serve           # start web UI at http://localhost:5000"
echo ""
echo "  To run unit tests (on host, no container needed):"
echo "       make test"
echo ""
echo "  To run integration tests (inside container):"
echo "       source /etc/yottadb/env && pytest tests/ -m integration"
