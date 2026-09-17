# LegalRAG Pro — Native local macOS runtime

This deployment layer runs the existing governed LegalRAG Pro application locally
on macOS without modifying its legal-analysis, evidence, drafting, authority,
professional-review, task, database or Chroma semantics.

## Supported target

- macOS
- Apple Silicon (`arm64`) is the primary target; Intel (`x86_64`) is accepted
- Homebrew
- Homebrew Python 3.14
- Poppler
- Tesseract plus `tesseract-lang` for Urdu
- Local Streamlit on `127.0.0.1:8501`

The macOS scripts deliberately use `.venv-macos`, leaving the Windows `.venv`
contract untouched.

## Install

From the repository root on the Mac:

```bash
chmod +x scripts/macos/*.sh
./scripts/macos/bootstrap.sh
```

Bootstrap installs missing Homebrew formulae:

- `python@3.14`
- `poppler`
- `tesseract`
- `tesseract-lang`

It then creates `.venv-macos`, installs `requirements-macos.lock`, and runs the
Mac doctor.

The installer does not fetch or create an OpenAI API key. Transfer your existing
`.env` securely or create one locally.

## Validate

```bash
./scripts/macos/doctor.sh
```

Success ends with:

`LEGALRAG_MACOS_DOCTOR_RESULT=PASS`

## Run

```bash
./scripts/macos/run.sh
```

or:

```bash
./scripts/macos/run.sh --no-browser
```

Success ends with:

`LEGALRAG_MACOS_RUN_RESULT=PASS`

Use:

`http://127.0.0.1:8501`

## Status

```bash
./scripts/macos/status.sh
```

## Stop

```bash
./scripts/macos/stop.sh
```

## Data migration

MAC1-I1 establishes and validates the native Mac runtime. Do not manually merge
Windows case stores into the Mac runtime yet. Case-data migration is the next
governed step so SQLite, Chroma, immutable evidence, receipts, authorities, tasks,
drafts, professional releases and reports can be verified exactly.
