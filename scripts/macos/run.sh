#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

legalrag_require_macos
legalrag_require_repo
legalrag_require_venv

NO_BROWSER=0
if [[ "${1:-}" == "--no-browser" ]]; then
  NO_BROWSER=1
fi

mkdir -p "${LEGALRAG_RUNTIME_DIR}"

if legalrag_health; then
  echo "LEGALRAG_RUNTIME_ALREADY_HEALTHY=PASS"
  echo "URL=${LEGALRAG_URL}"
  exit 0
fi

if [[ -f "${LEGALRAG_PID_FILE}" ]]; then
  OLD_PID="$(cat "${LEGALRAG_PID_FILE}" 2>/dev/null || true)"
  if [[ -n "${OLD_PID}" ]] && kill -0 "${OLD_PID}" >/dev/null 2>&1; then
    echo "STOP: PID file points to a running process but LegalRAG health is down: ${OLD_PID}" >&2
    exit 2
  fi
  rm -f "${LEGALRAG_PID_FILE}"
fi

cd "${LEGALRAG_REPO_ROOT}"

nohup "${LEGALRAG_PYTHON}" -B -m streamlit run src/app.py \
  --server.port 8501 \
  --server.address 127.0.0.1 \
  --server.headless true \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false \
  >"${LEGALRAG_STDOUT_LOG}" \
  2>"${LEGALRAG_STDERR_LOG}" &

PID=$!
echo "${PID}" > "${LEGALRAG_PID_FILE}"
echo "STARTED_RUNTIME_PID=${PID}"

for _ in $(seq 1 40); do
  if ! kill -0 "${PID}" >/dev/null 2>&1; then
    echo "STOP: LegalRAG runtime exited during startup." >&2
    tail -n 100 "${LEGALRAG_STDERR_LOG}" >&2 || true
    exit 1
  fi

  if legalrag_health; then
    echo "RUNTIME_HEALTH=PASS"
    echo "URL=${LEGALRAG_URL}"
    echo "STDOUT=${LEGALRAG_STDOUT_LOG}"
    echo "STDERR=${LEGALRAG_STDERR_LOG}"
    if [[ "${NO_BROWSER}" -eq 0 ]]; then
      open "${LEGALRAG_URL}" >/dev/null 2>&1 || true
    fi
    echo "LEGALRAG_MACOS_RUN_RESULT=PASS"
    exit 0
  fi
  sleep 1
done

echo "STOP: LegalRAG did not become healthy within 40 seconds." >&2
tail -n 100 "${LEGALRAG_STDERR_LOG}" >&2 || true
exit 1
