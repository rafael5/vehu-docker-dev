#!/usr/bin/env bash
# =============================================================================
# vehu-docker-config-check.sh
# VEHU Docker Environment Pre-Requisites Checker
#
# PURPOSE
#   Validates that the entire VEHU Docker development environment is correctly
#   configured and operational for the vista-fm-browser / FileMan Analysis
#   project. Checks both the host machine and the container internals.
#
# USAGE
#   Run from the HOST (checks host + re-runs itself inside the container):
#       bash vehu-docker-config-check.sh
#
#   Run from INSIDE the container (checks container only):
#       bash /opt/vista-fm-browser/vehu-docker-config-check.sh
#
#   Run with verbose output:
#       bash vehu-docker-config-check.sh --verbose
#
#   Run host checks only (skip container exec):
#       bash vehu-docker-config-check.sh --host-only
#
#   Run container checks only (must be inside container):
#       bash vehu-docker-config-check.sh --container-only
#
# WHAT IS CHECKED
#
#   HOST CHECKS (run from the host machine):
#     1.  Docker installed and version >= 20.x
#     2.  docker compose V2 plugin available
#     3.  User is in the 'docker' group (auto-fix offered)
#     4.  Container 'vehu' is running
#     5.  All expected port mappings present (5000, 8888, 9430, 1338, 8080)
#     6.  Project directory bind-mount is correct
#
#   CONTAINER CHECKS (run inside the vehu container):
#     7.  OS identity (Rocky Linux 8 / yottadb/octo-vehu base image)
#     8.  YottaDB environment variables set:
#           ydb_gbldir, ydb_routines, ydb_dir, ydb_dist
#     9.  YottaDB env-set script present and sourceable
#     10. YottaDB binary accessible and returns a version
#     11. YottaDB globals readable via Python:
#           ^DD  — FileMan data dictionary (must have entries)
#           ^DIC — FileMan file registry (must have entries)
#           ^DD(2,0) — PATIENT file header (key smoke test)
#     12. Python 3.12 at /opt/venv/bin/python
#     13. uv package manager installed and on PATH
#     14. Python runtime packages importable:
#           click, rich, flask, pandas, tabulate, yottadb
#     15. Python dev packages importable:
#           pytest, ruff, mypy
#     16. Python analysis packages importable:
#           matplotlib, networkx, numpy, jupyterlab, ipywidgets
#     17. fm-browser CLI registered and --help works
#     18. fm-browser files (live YottaDB query — the real smoke test)
#     19. Project source mounted at /opt/vista-fm-browser
#     20. All source modules present (connection, data_dictionary, etc.)
#     21. Analysis scripts present (scripts/analysis/phase1..8)
#     22. vista_fm_browser package importable as a module
#     23. Output data directory ~/data/vista-fm-browser/output/ (created if absent)
#     24. /etc/bashrc sources YottaDB env on interactive login
#     25. System tools: gcc, make, git, curl, vim/micro, ranger
#     26. Port listeners: Flask :5000 and Jupyter :8888 (advisory only)
#
# OUTPUT FORMAT
#   Each check prints one of:
#     [PASS]  — check succeeded
#     [WARN]  — non-fatal issue; a fix suggestion is printed
#     [FAIL]  — critical issue; a fix command is printed
#
#   Final summary shows total PASS / WARN / FAIL counts and overall status.
#   Exit code 0 = all checks passed or warned only.
#   Exit code 1 = one or more FAIL checks.
#
# AUTO-FIX
#   The script never modifies the system automatically, but prints the exact
#   command to fix each failure. The docker group membership check will offer
#   to run the fix with sudo if run interactively on the host.
#
# REQUIREMENTS
#   Host: bash 4+, docker 20+, docker compose V2
#   Container: already running (docker compose up -d)
#
# PROJECT CONTEXT
#   Container: vehu  (yottadb/octo-vehu base, Rocky Linux 8)
#   Project mount: /opt/vista-fm-browser  (host bind-mount)
#   Python venv: /opt/venv  (built into image, NOT the bind-mounted .venv/)
#   Data output: ~/data/vista-fm-browser/output/
#   Key ports: 5000=Flask, 8888=Jupyter, 9430=RPC, 1338=Rocto, 8080=YDB GUI
#
# =============================================================================

# Do NOT use set -e — this is a checker script that must continue through failures.
# Individual checks handle their own errors.

# ---------------------------------------------------------------------------
# CLI flags
# ---------------------------------------------------------------------------
VERBOSE=false
HOST_ONLY=false
CONTAINER_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --verbose)        VERBOSE=true ;;
        --host-only)      HOST_ONLY=true ;;
        --container-only) CONTAINER_ONLY=true ;;
        --help|-h)
            sed -n '3,80p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'
            exit 0
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Colors and formatting
# ---------------------------------------------------------------------------
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    DIM='\033[2m'
    RESET='\033[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' CYAN='' BOLD='' DIM='' RESET=''
fi

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
section() {
    echo
    echo -e "${BOLD}${BLUE}━━━  $1  ━━━${RESET}"
}

pass() {
    PASS_COUNT=$(( PASS_COUNT + 1 ))
    echo -e "  ${GREEN}[PASS]${RESET}  $1"
    [[ "$VERBOSE" == true && -n "${2:-}" ]] && echo -e "         ${DIM}$2${RESET}"
}

warn() {
    WARN_COUNT=$(( WARN_COUNT + 1 ))
    echo -e "  ${YELLOW}[WARN]${RESET}  $1"
    [[ -n "${2:-}" ]] && echo -e "         ${YELLOW}Fix:${RESET} ${DIM}$2${RESET}"
}

fail() {
    FAIL_COUNT=$(( FAIL_COUNT + 1 ))
    echo -e "  ${RED}[FAIL]${RESET}  $1"
    [[ -n "${2:-}" ]] && echo -e "         ${RED}Fix:${RESET} ${DIM}$2${RESET}"
}

info() {
    echo -e "         ${DIM}$1${RESET}"
}

check_cmd() {
    # check_cmd <description> <command...>
    local desc="$1"; shift
    if "$@" &>/dev/null; then
        pass "$desc"
        return 0
    else
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Detect whether we are on the host or inside the container
# ---------------------------------------------------------------------------
detect_environment() {
    if [[ -f /.dockerenv ]]; then
        echo "container"
    elif [[ -f /run/.containerenv ]]; then
        echo "container"
    elif grep -q "docker\|lxc" /proc/1/cgroup 2>/dev/null; then
        echo "container"
    else
        echo "host"
    fi
}

ENV_MODE=$(detect_environment)

# ===========================================================================
# HOST CHECKS
# ===========================================================================
run_host_checks() {
    echo
    echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}${CYAN}║   VEHU Docker Config Check — HOST ENVIRONMENT               ║${RESET}"
    echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════════════╝${RESET}"

    # -----------------------------------------------------------------------
    section "Docker Installation"
    # -----------------------------------------------------------------------

    # Docker binary
    if ! command -v docker &>/dev/null; then
        fail "docker not found on PATH" \
             "Install Docker: https://docs.docker.com/engine/install/"
        echo -e "\n${RED}Cannot continue without Docker. Aborting.${RESET}"
        exit 1
    fi

    DOCKER_VERSION=$(docker --version 2>/dev/null | grep -oP '\d+\.\d+' | head -1)
    DOCKER_MAJOR=$(echo "$DOCKER_VERSION" | cut -d. -f1)
    if [[ "$DOCKER_MAJOR" -ge 20 ]]; then
        pass "Docker installed: $(docker --version 2>/dev/null)" \
             "Version $DOCKER_VERSION >= 20 required"
    else
        fail "Docker version $DOCKER_VERSION is too old (need >= 20)" \
             "Upgrade Docker: https://docs.docker.com/engine/install/"
    fi

    # docker compose V2
    if docker compose version &>/dev/null; then
        pass "docker compose V2 available: $(docker compose version 2>/dev/null | head -1)"
    else
        fail "docker compose V2 not available" \
             "Install the compose plugin: https://docs.docker.com/compose/install/"
    fi

    # -----------------------------------------------------------------------
    section "Docker Group Membership"
    # -----------------------------------------------------------------------

    CURRENT_USER="${USER:-$(whoami)}"
    if groups "$CURRENT_USER" 2>/dev/null | grep -qw docker; then
        pass "User '$CURRENT_USER' is in the 'docker' group"
    else
        fail "User '$CURRENT_USER' is NOT in the 'docker' group" \
             "sudo usermod -aG docker $CURRENT_USER  (then log out and back in)"
        # Offer to fix if interactive
        if [[ -t 0 ]]; then
            echo
            echo -e "  ${YELLOW}Would you like to run the fix now? (requires sudo) [y/N]${RESET} \c"
            read -r ans
            if [[ "${ans,,}" == "y" ]]; then
                sudo usermod -aG docker "$CURRENT_USER"
                echo -e "  ${GREEN}Added. Log out and back in (or run: newgrp docker) for the change to take effect.${RESET}"
            fi
        fi
    fi

    # sudo-less docker socket access
    if docker info &>/dev/null; then
        pass "Docker socket accessible without sudo"
    else
        warn "Docker socket not accessible without sudo" \
             "newgrp docker  (or log out and back in after adding to docker group)"
    fi

    # -----------------------------------------------------------------------
    section "Container Status"
    # -----------------------------------------------------------------------

    # Container running
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^vehu$'; then
        pass "Container 'vehu' is running"
        CONTAINER_RUNNING=true
    else
        fail "Container 'vehu' is NOT running" \
             "cd $(pwd) && docker compose up -d"
        CONTAINER_RUNNING=false
    fi

    # Container image
    if [[ "$CONTAINER_RUNNING" == true ]]; then
        IMAGE=$(docker inspect vehu --format '{{.Config.Image}}' 2>/dev/null || echo "unknown")
        pass "Container image: $IMAGE"

        UPTIME=$(docker inspect vehu --format '{{.State.StartedAt}}' 2>/dev/null || echo "?")
        info "Started: $UPTIME"
    fi

    # -----------------------------------------------------------------------
    section "Port Mappings"
    # -----------------------------------------------------------------------

    declare -A EXPECTED_PORTS=(
        [5000]="Flask web UI (fm-browser serve)"
        [8888]="JupyterLab"
        [9430]="VistA RPC Broker"
        [1338]="Rocto SQL interface"
        [8080]="YottaDB GUI"
    )

    if [[ "$CONTAINER_RUNNING" == true ]]; then
        ACTUAL_PORTS=$(docker port vehu 2>/dev/null || echo "")
        for port in "${!EXPECTED_PORTS[@]}"; do
            if echo "$ACTUAL_PORTS" | grep -q ":${port}$\|:${port} "; then
                pass "Port $port mapped — ${EXPECTED_PORTS[$port]}"
            else
                warn "Port $port not mapped — ${EXPECTED_PORTS[$port]}" \
                     "Add \"${port}:${port}\" to docker-compose.yml ports, then docker compose up -d"
            fi
        done
    else
        warn "Cannot check ports — container not running"
    fi

    # -----------------------------------------------------------------------
    section "Project Bind-Mount"
    # -----------------------------------------------------------------------

    PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
    if [[ "$CONTAINER_RUNNING" == true ]]; then
        MOUNT_DEST=$(docker inspect vehu \
            --format '{{range .Mounts}}{{if eq .Destination "/opt/vista-fm-browser"}}{{.Source}}{{end}}{{end}}' \
            2>/dev/null || echo "")
        if [[ -n "$MOUNT_DEST" ]]; then
            pass "Project bind-mount: $MOUNT_DEST → /opt/vista-fm-browser"
        else
            fail "Project NOT mounted at /opt/vista-fm-browser in container" \
                 "Check volumes: section in docker-compose.yml"
        fi
    fi

    # docker-compose.yml present
    if [[ -f "$PROJECT_DIR/docker-compose.yml" ]]; then
        pass "docker-compose.yml found at $PROJECT_DIR"
    else
        fail "docker-compose.yml not found" \
             "Run from the project root directory"
    fi
}

# ===========================================================================
# CONTAINER CHECKS  (run inside the vehu container)
# ===========================================================================
run_container_checks() {
    echo
    echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}${CYAN}║   VEHU Docker Config Check — CONTAINER ENVIRONMENT          ║${RESET}"
    echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════════════╝${RESET}"

    # -----------------------------------------------------------------------
    section "Operating System"
    # -----------------------------------------------------------------------

    if [[ -f /etc/os-release ]]; then
        OS_NAME=$(. /etc/os-release && echo "$PRETTY_NAME")
        pass "OS: $OS_NAME"
        if echo "$OS_NAME" | grep -qi "rocky\|rhel\|centos\|alma"; then
            pass "Base OS family: RHEL-compatible (expected for yottadb/octo-vehu)"
        else
            warn "Unexpected OS: $OS_NAME (expected Rocky Linux 8)"
        fi
    else
        warn "Cannot read /etc/os-release"
    fi

    # Base image check via hostname
    HOSTNAME_VAL=$(hostname 2>/dev/null || echo "unknown")
    info "Hostname: $HOSTNAME_VAL"

    # Octo/VEHU presence
    if command -v octo &>/dev/null || [[ -f /usr/local/lib/yottadb/r2.05_x86_64/octo ]]; then
        pass "Octo (VistA SQL) is present"
    else
        warn "Octo binary not found (may be normal depending on image version)"
    fi

    # -----------------------------------------------------------------------
    section "YottaDB Environment Variables"
    # -----------------------------------------------------------------------

    YDB_ENV_OK=true

    check_ydb_var() {
        local var="$1"
        local val="${!var:-}"
        if [[ -n "$val" ]]; then
            pass "$var = $val"
        else
            fail "$var is NOT set" \
                 "source /usr/local/etc/ydb_env_set"
            YDB_ENV_OK=false
        fi
    }

    check_ydb_var ydb_gbldir
    check_ydb_var ydb_routines
    check_ydb_var ydb_dir
    check_ydb_var ydb_dist

    # gbldir file actually exists
    if [[ -n "${ydb_gbldir:-}" ]]; then
        if [[ -f "$ydb_gbldir" ]]; then
            pass "ydb_gbldir file exists: $ydb_gbldir"
        else
            fail "ydb_gbldir points to missing file: $ydb_gbldir" \
                 "source /usr/local/etc/ydb_env_set  (check YDB installation)"
            YDB_ENV_OK=false
        fi
    fi

    # ydb_dist directory
    if [[ -n "${ydb_dist:-}" ]]; then
        if [[ -d "$ydb_dist" ]]; then
            pass "ydb_dist directory exists: $ydb_dist"
        else
            fail "ydb_dist directory missing: $ydb_dist"
            YDB_ENV_OK=false
        fi
    fi

    # -----------------------------------------------------------------------
    section "YottaDB Environment Setup Script"
    # -----------------------------------------------------------------------

    YDB_ENV_SCRIPT="/usr/local/etc/ydb_env_set"
    if [[ -f "$YDB_ENV_SCRIPT" ]]; then
        pass "YDB env script present: $YDB_ENV_SCRIPT"
    else
        fail "YDB env script missing: $YDB_ENV_SCRIPT" \
             "Check if /etc/yottadb/env exists as an alternative"
        # Try alternate location
        if [[ -f "/etc/yottadb/env" ]]; then
            warn "Alternate found at /etc/yottadb/env — update scripts to use this path"
        fi
    fi

    # /etc/bashrc sources YDB on login
    if grep -q "ydb_env_set\|yottadb/env" /etc/bashrc 2>/dev/null; then
        pass "/etc/bashrc sources YottaDB environment on interactive login"
    else
        warn "/etc/bashrc does NOT source YDB env" \
             "Add: source /usr/local/etc/ydb_env_set to /etc/bashrc"
    fi

    # -----------------------------------------------------------------------
    section "YottaDB Binary"
    # -----------------------------------------------------------------------

    if [[ -n "${ydb_dist:-}" ]] && [[ -x "${ydb_dist}/yottadb" ]]; then
        YDB_VERSION=$("${ydb_dist}/yottadb" --version 2>/dev/null | head -1 || echo "unknown")
        pass "yottadb binary: ${ydb_dist}/yottadb"
        info "Version: $YDB_VERSION"
    elif command -v yottadb &>/dev/null; then
        YDB_VERSION=$(yottadb --version 2>/dev/null | head -1 || echo "unknown")
        pass "yottadb on PATH"
        info "Version: $YDB_VERSION"
    else
        fail "yottadb binary not found" \
             "Check \$ydb_dist or PATH — base image should include YottaDB"
    fi

    # -----------------------------------------------------------------------
    section "YottaDB Globals — Live Data Read"
    # -----------------------------------------------------------------------

    if [[ "$YDB_ENV_OK" == false ]]; then
        warn "Skipping global reads — YDB env vars not fully set" \
             "source /usr/local/etc/ydb_env_set  then re-run this script"
    else
        PYTHON_BIN="/opt/venv/bin/python"
        if [[ ! -x "$PYTHON_BIN" ]]; then
            PYTHON_BIN=$(command -v python3 2>/dev/null || echo "")
        fi

        if [[ -n "$PYTHON_BIN" ]]; then
            # Test ^DD exists (FileMan data dictionary)
            DD_COUNT=$("$PYTHON_BIN" -c "
import sys
try:
    import yottadb
    count = 0
    subs = ['']
    while True:
        try:
            sub = yottadb.subscript_next('^DD', subs)
            count += 1
            subs = [sub]
            if count >= 5:
                break
        except yottadb.YDBNodeEnd:
            break
    print(count)
except Exception as e:
    print('0')
" 2>/dev/null || echo "0")

            if [[ "$DD_COUNT" -gt 0 ]]; then
                pass "^DD global readable — FileMan data dictionary has entries"
            else
                fail "^DD global is empty or unreadable" \
                     "Ensure YDB env vars are set: source /usr/local/etc/ydb_env_set"
            fi

            # Test ^DIC exists (File registry)
            DIC_VAL=$("$PYTHON_BIN" -c "
import sys
try:
    import yottadb
    val = yottadb.get('^DIC', ['1', '0'])
    print(val[:30] if val else 'EMPTY')
except Exception as e:
    print('ERROR: ' + str(e))
" 2>/dev/null || echo "ERROR")

            if [[ "$DIC_VAL" == ERROR* ]] || [[ "$DIC_VAL" == "EMPTY" ]]; then
                fail "^DIC(1,0) not readable — File registry missing" \
                     "source /usr/local/etc/ydb_env_set  (^DIC must be accessible)"
            else
                pass "^DIC(1,0) readable — File registry (File #1 = $DIC_VAL)"
            fi

            # Test PATIENT file ^DD(2,0)
            PATIENT_HEADER=$("$PYTHON_BIN" -c "
try:
    import yottadb
    val = yottadb.get('^DD', ['2', '0'])
    print(val[:40] if val else 'EMPTY')
except Exception as e:
    print('ERROR')
" 2>/dev/null || echo "ERROR")

            if [[ "$PATIENT_HEADER" == ERROR ]] || [[ "$PATIENT_HEADER" == EMPTY ]]; then
                fail "^DD(2,0) not readable — PATIENT file header missing" \
                     "VEHU data may not be loaded. Check base image."
            else
                pass "^DD(2,0) readable — PATIENT file: $PATIENT_HEADER"
            fi

        else
            warn "Cannot test globals — no Python binary available yet"
        fi
    fi

    # -----------------------------------------------------------------------
    section "Python Environment"
    # -----------------------------------------------------------------------

    VENV_PYTHON="/opt/venv/bin/python"

    if [[ -x "$VENV_PYTHON" ]]; then
        pass "Python venv exists: /opt/venv"
        PY_VERSION=$("$VENV_PYTHON" --version 2>/dev/null || echo "unknown")
        info "Version: $PY_VERSION"

        PY_MAJOR_MINOR=$(echo "$PY_VERSION" | grep -oP '\d+\.\d+' | head -1)
        if [[ "$PY_MAJOR_MINOR" == "3.12" ]]; then
            pass "Python version is 3.12 (required)"
        else
            fail "Python version is $PY_MAJOR_MINOR (need 3.12)" \
                 "Rebuild the container: docker compose up -d --build"
        fi

        # pip inside venv
        if [[ -x "/opt/venv/bin/pip" ]]; then
            pass "/opt/venv/bin/pip is present"
        else
            warn "/opt/venv/bin/pip missing — use uv pip install instead"
        fi
    else
        fail "Python venv NOT found at /opt/venv" \
             "Rebuild the container image: docker compose up -d --build"
    fi

    # Verify venv is on PATH
    WHICH_PYTHON=$(command -v python 2>/dev/null || echo "")
    if [[ "$WHICH_PYTHON" == "/opt/venv/bin/python" ]]; then
        pass "python on PATH resolves to /opt/venv/bin/python"
    elif [[ -n "$WHICH_PYTHON" ]]; then
        warn "python on PATH is $WHICH_PYTHON (expected /opt/venv/bin/python)" \
             "export PATH=/opt/venv/bin:\$PATH  (should be in /etc/bashrc)"
    else
        warn "python not on PATH" \
             "export PATH=/opt/venv/bin:\$PATH"
    fi

    # -----------------------------------------------------------------------
    section "uv Package Manager"
    # -----------------------------------------------------------------------

    if command -v uv &>/dev/null; then
        UV_VERSION=$(uv --version 2>/dev/null || echo "unknown")
        pass "uv installed: $UV_VERSION"
        info "Path: $(command -v uv)"
    elif [[ -x "/root/.local/bin/uv" ]]; then
        pass "uv installed at /root/.local/bin/uv"
        UV_VERSION=$(/root/.local/bin/uv --version 2>/dev/null || echo "unknown")
        info "Version: $UV_VERSION"
    else
        fail "uv not found" \
             "curl -LsSf https://astral.sh/uv/install.sh | sh"
    fi

    # -----------------------------------------------------------------------
    section "Python Packages — Runtime"
    # -----------------------------------------------------------------------

    check_python_import() {
        local pkg="$1"
        local import_name="${2:-$1}"
        local version_attr="${3:-__version__}"
        if [[ ! -x "$VENV_PYTHON" ]]; then
            warn "Cannot check $pkg — no Python binary"
            return
        fi
        local version
        version=$("$VENV_PYTHON" -c "
import $import_name
try:
    v = getattr($import_name, '$version_attr', None) or getattr($import_name, 'VERSION', '?')
    print(str(v)[:20])
except Exception:
    print('ok')
" 2>/dev/null) || version=""

        if [[ -n "$version" ]]; then
            pass "$pkg importable (v$version)"
        else
            fail "$pkg NOT importable" \
                 "uv pip install '$pkg' (inside container)"
        fi
    }

    check_python_import "click"
    check_python_import "rich"
    check_python_import "flask" "flask" "__version__"
    check_python_import "pandas"
    check_python_import "tabulate"
    check_python_import "yottadb" "yottadb" "__version__"

    # -----------------------------------------------------------------------
    section "Python Packages — Dev Tools"
    # -----------------------------------------------------------------------

    check_python_import "pytest"
    check_python_import "ruff"
    check_python_import "mypy"

    # -----------------------------------------------------------------------
    section "Python Packages — Analysis / Visualization"
    # -----------------------------------------------------------------------

    check_python_import "matplotlib"
    check_python_import "networkx"
    check_python_import "numpy"
    check_python_import "jupyterlab" "jupyterlab" "__version__"
    check_python_import "ipywidgets"

    # -----------------------------------------------------------------------
    section "fm-browser CLI"
    # -----------------------------------------------------------------------

    FM_BROWSER="/opt/venv/bin/fm-browser"
    if [[ -x "$FM_BROWSER" ]]; then
        pass "fm-browser entry point: $FM_BROWSER"
    elif command -v fm-browser &>/dev/null; then
        pass "fm-browser on PATH: $(command -v fm-browser)"
    else
        fail "fm-browser not found" \
             "uv pip install -e '/opt/vista-fm-browser[dev]' -q"
    fi

    # fm-browser --help
    if "$FM_BROWSER" --help &>/dev/null 2>&1 || \
       (command -v fm-browser &>/dev/null && fm-browser --help &>/dev/null 2>&1); then
        pass "fm-browser --help works"
    else
        fail "fm-browser --help failed" \
             "uv pip install -e '/opt/vista-fm-browser[dev]' -q"
    fi

    # fm-browser files — live data test (only if YDB env is OK)
    if [[ "$YDB_ENV_OK" == true ]]; then
        FM_OUT=$("$FM_BROWSER" files --limit 3 2>&1 || echo "ERROR")
        if echo "$FM_OUT" | grep -qiE "error|traceback|exception|not found"; then
            fail "fm-browser files failed (live YDB query)" \
                 "Check YDB env vars and that ^DIC global is readable"
            [[ "$VERBOSE" == true ]] && info "Output: $(echo "$FM_OUT" | head -5)"
        else
            pass "fm-browser files (live YottaDB query) — OK"
            if [[ "$VERBOSE" == true ]]; then
                echo "$FM_OUT" | head -5 | while IFS= read -r line; do info "$line"; done
            fi
        fi
    else
        warn "Skipping fm-browser files test — YDB env not complete"
    fi

    # -----------------------------------------------------------------------
    section "Project Source Mount"
    # -----------------------------------------------------------------------

    PROJECT="/opt/vista-fm-browser"

    if [[ -d "$PROJECT" ]]; then
        pass "Project directory exists: $PROJECT"
    else
        fail "Project directory missing: $PROJECT" \
             "Check volumes: in docker-compose.yml and restart: docker compose up -d"
    fi

    declare -A EXPECTED_MODULES=(
        ["src/vista_fm_browser/__init__.py"]="Package init"
        ["src/vista_fm_browser/connection.py"]="YdbConnection"
        ["src/vista_fm_browser/data_dictionary.py"]="DataDictionary"
        ["src/vista_fm_browser/file_reader.py"]="FileReader"
        ["src/vista_fm_browser/inventory.py"]="FileInventory"
        ["src/vista_fm_browser/exporter.py"]="Exporter"
        ["src/vista_fm_browser/cli.py"]="CLI entry point"
        ["src/vista_fm_browser/web/app.py"]="Flask web app"
    )

    for rel_path in "${!EXPECTED_MODULES[@]}"; do
        desc="${EXPECTED_MODULES[$rel_path]}"
        if [[ -f "$PROJECT/$rel_path" ]]; then
            pass "$desc: $rel_path"
        else
            fail "$desc missing: $PROJECT/$rel_path" \
                 "Check bind-mount — host project directory may not contain this file"
        fi
    done

    # vista_fm_browser importable as a module
    if [[ -x "$VENV_PYTHON" ]]; then
        if "$VENV_PYTHON" -c "import vista_fm_browser" &>/dev/null; then
            pass "vista_fm_browser package importable"
        else
            fail "vista_fm_browser NOT importable" \
                 "uv pip install -e '/opt/vista-fm-browser[dev]' -q"
        fi
    fi

    # -----------------------------------------------------------------------
    section "Analysis Scripts"
    # -----------------------------------------------------------------------

    SCRIPTS_DIR="$PROJECT/scripts/analysis"
    if [[ -d "$SCRIPTS_DIR" ]]; then
        pass "Analysis scripts directory: $SCRIPTS_DIR"
        for phase in 1 2 3 4 5 6 7 8; do
            script=$(ls "$SCRIPTS_DIR"/phase${phase}_*.py 2>/dev/null | head -1)
            if [[ -n "$script" ]]; then
                pass "Phase $phase script: $(basename "$script")"
            else
                fail "Phase $phase script missing from $SCRIPTS_DIR" \
                     "git pull — scripts/analysis/phase${phase}_*.py should exist"
            fi
        done
    else
        fail "Analysis scripts directory missing: $SCRIPTS_DIR" \
             "git pull or check the project mount"
    fi

    # Visualization scripts
    for vscript in "scripts/to_treemap.py" "scripts/viz_library.py"; do
        if [[ -f "$PROJECT/$vscript" ]]; then
            pass "Visualization: $vscript"
        else
            warn "$vscript not found" \
                 "git pull to restore"
        fi
    done

    # -----------------------------------------------------------------------
    section "Data Output Directories"
    # -----------------------------------------------------------------------

    DATA_BASE="$HOME/data/vista-fm-browser"
    for subdir in output input db; do
        dir="$DATA_BASE/$subdir"
        if [[ -d "$dir" ]]; then
            pass "Data directory exists: $dir"
        else
            warn "Data directory missing: $dir (creating...)" \
                 "mkdir -p $dir"
            mkdir -p "$dir"
            if [[ -d "$dir" ]]; then
                info "Created: $dir"
            fi
        fi
    done

    # Check output writable
    TEST_FILE="$DATA_BASE/output/.write_test_$$"
    if touch "$TEST_FILE" 2>/dev/null; then
        rm -f "$TEST_FILE"
        pass "Output directory is writable: $DATA_BASE/output/"
    else
        fail "Output directory is NOT writable: $DATA_BASE/output/" \
             "chmod 755 $DATA_BASE/output/"
    fi

    # -----------------------------------------------------------------------
    section "System Tools"
    # -----------------------------------------------------------------------

    check_system_tool() {
        local tool="$1"
        local pkg="${2:-$1}"
        if command -v "$tool" &>/dev/null; then
            local ver
            ver=$("$tool" --version 2>/dev/null | head -1 || echo "installed")
            pass "$tool: $ver"
        else
            warn "$tool not found" \
                 "dnf install -y $pkg  (inside container)"
        fi
    }

    check_system_tool "git"
    check_system_tool "gcc"
    check_system_tool "make"
    check_system_tool "curl"

    # vim or micro (at least one editor)
    if command -v micro &>/dev/null; then
        pass "micro editor: $(micro --version 2>/dev/null | head -1 || echo 'installed')"
    elif command -v vim &>/dev/null; then
        pass "vim editor available"
    else
        warn "No editor (micro/vim) found" \
             "dnf install -y micro  (inside container)"
    fi

    # ranger file manager
    if command -v ranger &>/dev/null; then
        pass "ranger file manager: $(ranger --version 2>/dev/null | head -1 || echo 'installed')"
    else
        warn "ranger file manager not found" \
             "dnf install -y ranger  (inside container)"
    fi

    # -----------------------------------------------------------------------
    section "Port Listeners (Advisory)"
    # -----------------------------------------------------------------------

    check_port_listening() {
        local port="$1"
        local desc="$2"
        if ss -tlnp 2>/dev/null | grep -q ":${port} " || \
           netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
            pass "Port $port listening — $desc is running"
        else
            info "Port $port not listening — $desc not started (normal if not in use)"
        fi
    }

    check_port_listening 5000 "Flask (fm-browser serve)"
    check_port_listening 8888 "JupyterLab"
    check_port_listening 9430 "VistA RPC Broker"
    check_port_listening 1338 "Rocto SQL"
    check_port_listening 8080 "YottaDB GUI"
}

# ===========================================================================
# SUMMARY
# ===========================================================================
print_summary() {
    echo
    echo -e "${BOLD}${BLUE}━━━  Summary  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo
    echo -e "  ${GREEN}PASS${RESET}  $PASS_COUNT"
    echo -e "  ${YELLOW}WARN${RESET}  $WARN_COUNT"
    echo -e "  ${RED}FAIL${RESET}  $FAIL_COUNT"
    echo

    if [[ "$FAIL_COUNT" -eq 0 && "$WARN_COUNT" -eq 0 ]]; then
        echo -e "  ${GREEN}${BOLD}✓  All checks passed. Environment is ready.${RESET}"
    elif [[ "$FAIL_COUNT" -eq 0 ]]; then
        echo -e "  ${YELLOW}${BOLD}⚠  No failures, but $WARN_COUNT warning(s). Review above.${RESET}"
    else
        echo -e "  ${RED}${BOLD}✗  $FAIL_COUNT check(s) FAILED. Fix the issues above and re-run.${RESET}"
    fi
    echo
    if [[ "$FAIL_COUNT" -gt 0 ]]; then
        echo -e "  ${DIM}Quick fixes:"
        echo -e "    source /usr/local/etc/ydb_env_set"
        echo -e "    uv pip install -e '/opt/vista-fm-browser[dev,analysis]' -q"
        echo -e "    python scripts/analysis/phase1_scope.py${RESET}"
        echo
    fi
}

# ===========================================================================
# MAIN — dispatch based on environment and flags
# ===========================================================================

if [[ "$CONTAINER_ONLY" == true ]]; then
    # Force container mode regardless of detection
    run_container_checks
    print_summary
    [[ "$FAIL_COUNT" -gt 0 ]] && exit 1 || exit 0
fi

if [[ "$ENV_MODE" == "container" ]]; then
    # Inside the container
    run_container_checks
    print_summary
    [[ "$FAIL_COUNT" -gt 0 ]] && exit 1 || exit 0
fi

# Running on the host
run_host_checks

if [[ "$HOST_ONLY" == true ]]; then
    print_summary
    [[ "$FAIL_COUNT" -gt 0 ]] && exit 1 || exit 0
fi

# Re-run the container checks inside the container
echo
echo -e "${BOLD}${BLUE}━━━  Running container checks inside 'vehu'  ━━━━━━━━━━━━━━━━━━${RESET}"

if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^vehu$'; then
    warn "Container 'vehu' not running — cannot run container checks" \
         "docker compose up -d"
    print_summary
    [[ "$FAIL_COUNT" -gt 0 ]] && exit 1 || exit 0
fi

SCRIPT_IN_CONTAINER="/opt/vista-fm-browser/$(basename "$0")"

# Check if the script is accessible inside the container
if docker exec vehu test -f "$SCRIPT_IN_CONTAINER" 2>/dev/null; then
    # Preserve YDB env by sourcing inside the exec
    docker exec -it vehu bash -c \
        "source /usr/local/etc/ydb_env_set 2>/dev/null || true; \
         bash '$SCRIPT_IN_CONTAINER' --container-only ${VERBOSE:+--verbose}"
else
    # Script not mounted — copy it in via stdin
    echo -e "${DIM}  (script not mounted in container — streaming via stdin)${RESET}"
    docker exec -i vehu bash -c \
        "source /usr/local/etc/ydb_env_set 2>/dev/null || true; \
         cat > /tmp/vehu-check.sh && bash /tmp/vehu-check.sh --container-only ${VERBOSE:+--verbose}" \
        < "$0"
fi

# Collect exit code from docker exec
CONTAINER_EXIT=$?
echo
print_summary
[[ "$CONTAINER_EXIT" -ne 0 || "$FAIL_COUNT" -gt 0 ]] && exit 1 || exit 0
