from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAC = ROOT / "scripts" / "macos"


def text(name: str) -> str:
    return (MAC / name).read_text(encoding="utf-8")


def test_mac_runtime_package_is_complete():
    for rel in (
        ".env.macos.example",
        "README-MACOS.md",
        "requirements-macos.lock",
        "scripts/macos/common.sh",
        "scripts/macos/bootstrap.sh",
        "scripts/macos/doctor.sh",
        "scripts/macos/run.sh",
        "scripts/macos/status.sh",
        "scripts/macos/stop.sh",
    ):
        assert (ROOT / rel).is_file(), rel


def test_mac_scripts_use_native_venv_and_do_not_depend_on_powershell():
    joined = "\n".join(
        text(name)
        for name in (
            "common.sh",
            "bootstrap.sh",
            "doctor.sh",
            "run.sh",
            "status.sh",
            "stop.sh",
        )
    ).lower()

    assert ".venv-macos" in joined
    assert ".venv\\\\scripts" not in joined
    assert "powershell.exe" not in joined
    assert "get-nettcpconnection" not in joined
    assert "get-ciminstance" not in joined


def test_bootstrap_binds_current_python_and_ocr_dependencies():
    source = text("bootstrap.sh")
    for token in (
        "python@3.14",
        "poppler",
        "tesseract",
        "tesseract-lang",
        "requirements-macos.lock",
        "doctor.sh",
    ):
        assert token in source


def test_common_maps_existing_localappdata_contract_to_application_support():
    source = text("common.sh")
    assert "Library/Application Support" in source
    assert "export LOCALAPPDATA=" in source
    assert "LEGALRAG_POPPLER_PATH" in source
    assert "PYTHONPATH" in source


def test_doctor_validates_sqlite_chroma_ocr_and_core_versions():
    source = text("doctor.sh")
    for token in (
        "chromadb",
        "streamlit",
        "openai",
        "sqlite3",
        "PersistentClient",
        "onnxruntime",
        "pyarrow",
        "TESSERACT_URDU_LANGUAGE",
        "LEGALRAG_POPPLER_PATH_BINDING",
        "LEGALRAG_MACOS_DOCTOR_RESULT=PASS",
    ):
        assert token in source


def test_run_is_local_only_and_preserves_streamlit_runtime_contract():
    source = text("run.sh")
    for token in (
        "127.0.0.1",
        "8501",
        "--server.headless",
        "--server.fileWatcherType",
        "--browser.gatherUsageStats",
        "src/app.py",
        "LEGALRAG_MACOS_RUN_RESULT=PASS",
    ):
        assert token in source


def test_stop_refuses_to_kill_unidentified_process():
    source = text("stop.sh")
    assert "Refusing to kill an unidentified process." in source
    assert "streamlit run src/app.py" in source


def test_lock_contains_required_production_pins():
    source = (ROOT / "requirements-macos.lock").read_text(encoding="utf-8")
    for pin in (
        "chromadb==1.5.9",
        "streamlit==1.60.0",
        "openai==2.50.0",
        "pytesseract==0.3.13",
        "pdf2image==1.17.0",
    ):
        assert pin in source


def test_env_template_contains_no_live_secret():
    source = (ROOT / ".env.macos.example").read_text(encoding="utf-8")
    assert "# OPENAI_API_KEY=" in source
