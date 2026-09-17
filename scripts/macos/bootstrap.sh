#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

legalrag_require_macos
legalrag_require_repo

ARCH="$(uname -m)"
echo "LEGALRAG_MACOS_ARCH=${ARCH}"

if [[ "${ARCH}" != "arm64" && "${ARCH}" != "x86_64" ]]; then
  echo "STOP: unsupported macOS architecture: ${ARCH}" >&2
  exit 2
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "STOP: Homebrew is required but was not found." >&2
  echo "Install Homebrew from https://brew.sh/ and rerun this script." >&2
  exit 2
fi

REQUIRED_FORMULAE=(python@3.14 poppler tesseract tesseract-lang)

for formula in "${REQUIRED_FORMULAE[@]}"; do
  if brew list --formula "${formula}" >/dev/null 2>&1; then
    echo "HOMEBREW_${formula}=PRESENT"
  else
    echo "Installing Homebrew dependency: ${formula}"
    brew install "${formula}"
  fi
done

PYTHON_PREFIX="$(brew --prefix python@3.14)"
PYTHON_BIN="${PYTHON_PREFIX}/bin/python3.14"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "STOP: Homebrew python3.14 was not found at ${PYTHON_BIN}" >&2
  exit 2
fi

PYTHON_VERSION="$("${PYTHON_BIN}" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
echo "MACOS_BOOTSTRAP_PYTHON=${PYTHON_VERSION}"

if [[ ! -d "${LEGALRAG_VENV}" ]]; then
  "${PYTHON_BIN}" -m venv "${LEGALRAG_VENV}"
  echo "MACOS_VENV_CREATED=PASS"
else
  echo "MACOS_VENV_ALREADY_PRESENT=PASS"
fi

"${LEGALRAG_PYTHON}" -m pip install --upgrade pip wheel
"${LEGALRAG_PYTHON}" -m pip install -r "${LEGALRAG_REPO_ROOT}/requirements-macos.lock"

mkdir -p "${LOCALAPPDATA}/LegalRAG" "${LEGALRAG_RUNTIME_DIR}"

if [[ ! -f "${LEGALRAG_REPO_ROOT}/.env" ]]; then
  echo "NOTICE: ${LEGALRAG_REPO_ROOT}/.env does not exist."
  echo "Copy your existing LegalRAG .env to the Mac securely before using OpenAI-backed features."
fi

"${SCRIPT_DIR}/doctor.sh"

echo "LEGALRAG_MACOS_BOOTSTRAP_RESULT=PASS"
