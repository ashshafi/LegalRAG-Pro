#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

legalrag_require_macos
legalrag_require_repo

if [[ ! -f "${LEGALRAG_PID_FILE}" ]]; then
  if legalrag_health; then
    echo "STOP: LegalRAG is healthy on port 8501 but no governed PID file exists." >&2
    echo "Refusing to kill an unidentified process." >&2
    exit 2
  fi
  echo "LEGALRAG_RUNTIME_ALREADY_STOPPED=PASS"
  exit 0
fi

PID="$(cat "${LEGALRAG_PID_FILE}" 2>/dev/null || true)"

if [[ ! "${PID}" =~ ^[0-9]+$ ]]; then
  echo "STOP: invalid LegalRAG PID file." >&2
  exit 2
fi

if ! kill -0 "${PID}" >/dev/null 2>&1; then
  rm -f "${LEGALRAG_PID_FILE}"
  echo "LEGALRAG_RUNTIME_ALREADY_STOPPED=PASS"
  exit 0
fi

COMMAND="$(ps -p "${PID}" -o command= 2>/dev/null || true)"
if [[ "${COMMAND}" != *"streamlit run src/app.py"* ]]; then
  echo "STOP: PID ${PID} does not identify the expected LegalRAG Streamlit command." >&2
  echo "COMMAND=${COMMAND}" >&2
  exit 2
fi

kill "${PID}"

for _ in $(seq 1 20); do
  if ! kill -0 "${PID}" >/dev/null 2>&1; then
    rm -f "${LEGALRAG_PID_FILE}"
    echo "LEGALRAG_MACOS_STOP_RESULT=PASS"
    exit 0
  fi
  sleep 0.5
done

echo "STOP: LegalRAG runtime did not stop cleanly." >&2
exit 1
