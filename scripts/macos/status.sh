#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

legalrag_require_macos
legalrag_require_repo

if legalrag_health; then
  echo "LEGALRAG_RUNTIME_HEALTH=PASS"
  echo "URL=${LEGALRAG_URL}"
  if [[ -f "${LEGALRAG_PID_FILE}" ]]; then
    echo "PID=$(cat "${LEGALRAG_PID_FILE}")"
  fi
  exit 0
fi

echo "LEGALRAG_RUNTIME_HEALTH=DOWN"
if [[ -f "${LEGALRAG_PID_FILE}" ]]; then
  echo "PID_FILE=${LEGALRAG_PID_FILE}"
  echo "PID=$(cat "${LEGALRAG_PID_FILE}" 2>/dev/null || true)"
fi
exit 1
