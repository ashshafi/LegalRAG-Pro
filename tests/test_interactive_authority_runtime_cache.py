from pathlib import Path

def test_provider_runtime_reuse_is_opt_in():
    source = Path("src/governed_analytical_authority/provider.py").read_text(encoding="utf-8-sig")
    assert "reuse_validated_runtime_authority: bool = False" in source

def test_interactive_assistant_opts_into_runtime_reuse():
    source = Path("src/legalrag.py").read_text(encoding="utf-8-sig")
    assert "reuse_validated_runtime_authority=True" in source

def test_fast_path_binds_current_pointer_to_cached_receipt():
    source = Path("src/governed_analytical_authority/provider.py").read_text(encoding="utf-8-sig")
    assert "current_active_payload = _read_utf8(active_path, root=governed_root)" in source
    assert "cached.authority.activation_receipt.new_active_pointer_sha256" in source
    assert "canonical_sha256(current_active_payload) == expected_active_sha256" in source

def test_strict_full_fingerprint_path_retained():
    source = Path("src/governed_analytical_authority/provider.py").read_text(encoding="utf-8-sig")
    assert "current_fingerprint = _runtime_cache_fingerprint(" in source
    assert "if current_fingerprint == cached.fingerprint:" in source
