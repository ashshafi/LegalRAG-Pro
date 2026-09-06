from pathlib import Path


def _case_source() -> str:
    return Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")


def test_r30_handles_rate_limit_without_task_work_persistence():
    source = _case_source()

    assert "from openai import APITimeoutError, RateLimitError" in source
    assert "if isinstance(exc, RateLimitError):" in source
    assert "No new task work was recorded." in source
    assert "API credit is unavailable" in source

    start = source.index("if isinstance(exc, RateLimitError):")
    end = source.index("\n            raise", start)
    block = source[start:end]

    assert "append_task_work_progress(" not in block
    assert "update_task(" not in block
    assert "TaskStatus.COMPLETED" not in block


def test_r30_distinguishes_quota_exhaustion_from_temporary_rate_limit():
    source = _case_source()

    assert '"insufficient_quota"' in source
    assert '"credit_balance_exhausted"' in source
    assert '"no credits remaining"' in source
    assert "temporarily rate limiting this request" in source


def test_r30_preserves_timeout_handling():
    source = _case_source()

    assert "if isinstance(exc, APITimeoutError):" in source
    assert "did not return this task investigation within" in source


def test_r30_provider_errors_return_before_task_work_persistence():
    source = _case_source()

    render_start = source.index("def _render_approved_task_execution(")
    render_end = source.index("\ndef ", render_start + 1)
    block = source[render_start:render_end]

    rate_limit_pos = block.index("if isinstance(exc, RateLimitError):")
    persist_pos = block.index("_persist_task_work_result(")
    assert rate_limit_pos < persist_pos


def test_r30_keeps_status_approval_gate():
    source = _case_source()

    assert '"Approve completion"' in source
    assert '"Mark in progress"' in source
    assert source.count("update_task(") == 1
