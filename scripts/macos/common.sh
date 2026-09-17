#!/usr/bin/env bash
set -euo pipefail

LEGALRAG_MACOS_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEGALRAG_REPO_ROOT="$(cd "${LEGALRAG_MACOS_SCRIPT_DIR}/../.." && pwd)"
LEGALRAG_VENV="${LEGALRAG_REPO_ROOT}/.venv-macos"
LEGALRAG_PYTHON="${LEGALRAG_VENV}/bin/python"
LEGALRAG_URL="http://127.0.0.1:8501"
LEGALRAG_HEALTH_URL="${LEGALRAG_URL}/_stcore/health"

export LOCALAPPDATA="${LOCALAPPDATA:-${HOME}/Library/Application Support}"
export LEGALRAG_MACOS_DATA_BASE="${LOCALAPPDATA}"
export PYTHONPATH="${LEGALRAG_REPO_ROOT}:${LEGALRAG_REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
export PYTHONDONTWRITEBYTECODE=1

LEGALRAG_RUNTIME_DIR="${LOCALAPPDATA}/LegalRAG/runtime"
LEGALRAG_PID_FILE="${LEGALRAG_RUNTIME_DIR}/streamlit.pid"
LEGALRAG_STDOUT_LOG="${LEGALRAG_RUNTIME_DIR}/streamlit.stdout.log"
LEGALRAG_STDERR_LOG="${LEGALRAG_RUNTIME_DIR}/streamlit.stderr.log"

if command -v brew >/dev/null 2>&1; then
  POPPLER_PREFIX="$(brew --prefix poppler 2>/dev/null || true)"
  if [[ -n "${POPPLER_PREFIX}" ]]; then
    export LEGALRAG_POPPLER_PATH="${LEGALRAG_POPPLER_PATH:-${POPPLER_PREFIX}/bin}"
    export PATH="${POPPLER_PREFIX}/bin:${PATH}"
  fi
fi

legalrag_require_macos() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "STOP: this script is for macOS (Darwin)." >&2
    exit 2
  fi
}

legalrag_require_repo() {
  if [[ ! -f "${LEGALRAG_REPO_ROOT}/src/app.py" ]]; then
    echo "STOP: LegalRAG repository root could not be resolved." >&2
    exit 2
  fi
}

legalrag_require_venv() {
  if [[ ! -x "${LEGALRAG_PYTHON}" ]]; then
    echo "STOP: macOS virtual environment is missing." >&2
    echo "Run: ./scripts/macos/bootstrap.sh" >&2
    exit 2
  fi
}

legalrag_health() {
  curl --silent --show-error --fail --max-time 2 "${LEGALRAG_HEALTH_URL}" >/dev/null 2>&1
}
