from pathlib import Path


def test_r27_case_operator_handles_provider_timeout_without_persistence():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")

    assert "from openai import APITimeoutError" in source
    assert "isinstance(exc, APITimeoutError)" in source
    assert "No new task work was recorded." in source

    render_start = source.index("def _render_approved_task_execution(")
    render_end = source.index("\ndef ", render_start + 1)
    block = source[render_start:render_end]

    timeout_pos = block.index("except Exception as exc:")
    persist_pos = block.index("_persist_task_work_result(")
    assert timeout_pos < persist_pos


def test_r27_timeout_handler_does_not_change_task_status():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")
    render_start = source.index("def _render_approved_task_execution(")
    render_end = source.index("\ndef ", render_start + 1)
    block = source[render_start:render_end]

    timeout_start = block.index("except Exception as exc:")
    timeout_end = block.index("st.session_state[_TASK_EXECUTION_CASE_KEY]", timeout_start)
    timeout_block = block[timeout_start:timeout_end]

    assert "update_task(" not in timeout_block
    assert "append_task_work_progress(" not in timeout_block
    assert "TaskStatus.COMPLETED" not in timeout_block


def test_r27_bounded_provider_telemetry_exposes_fanout():
    source = Path("src/bounded_governed_answer.py").read_text(encoding="utf-8-sig")

    assert "LEGALRAG_TIMING BOUNDED_BATCH_COUNT=" in source
    assert "LEGALRAG_TIMING BOUNDED_MAP_START " in source
    assert "PROMPT_CHARS=" in source
    assert "LEGALRAG_TIMING BOUNDED_MAP_FAILED " in source
    assert "LEGALRAG_TIMING BOUNDED_REDUCE_START " in source
    assert "LEGALRAG_TIMING BOUNDED_REDUCE_FAILED " in source
    assert "LEGALRAG_TIMING BOUNDED_TOTAL_MS=" in source


def test_r27_bounded_algorithm_constants_unchanged():
    import ast

    source = Path("src/bounded_governed_answer.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(source)

    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    try:
                        values[target.id] = ast.literal_eval(node.value)
                    except Exception:
                        pass
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            try:
                values[node.target.id] = ast.literal_eval(node.value)
            except Exception:
                pass

    assert values["BOUNDED_ANSWER_TRIGGER_CHARS"] == 500_000
    assert values["BOUNDED_BATCH_TARGET_CHARS"] == 240_000
    assert values["MAP_MAX_OUTPUT_TOKENS"] == 5_000
    assert values["REDUCE_MAX_OUTPUT_TOKENS"] == 8_000
