#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

legalrag_require_macos
legalrag_require_repo
legalrag_require_venv

FAIL=0

check_command() {
  local name="$1"
  if command -v "${name}" >/dev/null 2>&1; then
    echo "COMMAND_${name}=PASS"
  else
    echo "COMMAND_${name}=FAIL"
    FAIL=1
  fi
}

echo "LEGALRAG_MACOS_ARCH=$(uname -m)"
echo "LEGALRAG_MACOS_VERSION=$(sw_vers -productVersion)"
echo "LEGALRAG_REPO_ROOT=${LEGALRAG_REPO_ROOT}"
echo "LEGALRAG_DATA_BASE=${LOCALAPPDATA}"
echo "LEGALRAG_POPPLER_PATH=${LEGALRAG_POPPLER_PATH:-}"

check_command curl
check_command pdftoppm
check_command pdfinfo
check_command tesseract

"${LEGALRAG_PYTHON}" - <<'PY'
from __future__ import annotations

import importlib.metadata
import sqlite3
import sys
import tempfile
from pathlib import Path

EXPECTED = {
    "chromadb": "1.5.9",
    "streamlit": "1.60.0",
    "openai": "2.50.0",
    "pytesseract": "0.3.13",
    "pdf2image": "1.17.0",
}

print("PYTHON_VERSION=" + sys.version.split()[0])
if sys.version_info[:2] != (3, 14):
    raise SystemExit("STOP: LegalRAG macOS runtime requires Python 3.14.x")

for distribution, expected in EXPECTED.items():
    actual = importlib.metadata.version(distribution)
    if actual != expected:
        raise SystemExit(
            f"STOP: {distribution} version mismatch: expected={expected} got={actual}"
        )
    print(f"PACKAGE_{distribution}=PASS:{actual}")

import chromadb
import onnxruntime
import pyarrow
import streamlit
import openai
import pytesseract
import pdf2image

with sqlite3.connect(":memory:") as db:
    db.execute("create table doctor (id integer primary key, value text)")
    db.execute("insert into doctor(value) values ('ok')")
    value = db.execute("select value from doctor").fetchone()[0]
    if value != "ok":
        raise SystemExit("STOP: sqlite in-memory test failed")
print("SQLITE_RUNTIME=PASS")

with tempfile.TemporaryDirectory(prefix="legalrag-mac-doctor-") as td:
    client = chromadb.PersistentClient(path=str(Path(td) / "chroma"))
    collection = client.get_or_create_collection(
        "legalrag_mac_doctor",
        embedding_function=None,
    )
    collection.add(
        ids=["doctor-1"],
        documents=["macOS doctor"],
        embeddings=[[1.0, 0.0, 0.0]],
    )
    result = collection.get(ids=["doctor-1"])
    if result.get("ids") != ["doctor-1"]:
        raise SystemExit("STOP: Chroma local persistence test failed")
print("CHROMA_LOCAL_PERSISTENCE=PASS")

print("ONNXRUNTIME_IMPORT=PASS")
print("PYARROW_IMPORT=PASS")
print("STREAMLIT_IMPORT=PASS")
print("OPENAI_IMPORT=PASS")
print("OCR_PYTHON_IMPORTS=PASS")
PY

if tesseract --list-langs 2>/dev/null | grep -Fxq "urd"; then
  echo "TESSERACT_URDU_LANGUAGE=PASS"
else
  echo "TESSERACT_URDU_LANGUAGE=FAIL"
  FAIL=1
fi

if [[ ! -x "${LEGALRAG_POPPLER_PATH:-}/pdftoppm" ]]; then
  echo "LEGALRAG_POPPLER_PATH_BINDING=FAIL"
  FAIL=1
else
  echo "LEGALRAG_POPPLER_PATH_BINDING=PASS"
fi

if [[ "${FAIL}" -ne 0 ]]; then
  echo "LEGALRAG_MACOS_DOCTOR_RESULT=FAIL"
  exit 1
fi

echo "LEGALRAG_MACOS_DOCTOR_RESULT=PASS"
