"""Solicitor-facing native Case Operator over existing governed LegalRAG services.

R5 is deliberately non-authoritative:
- deterministic opening orientation selects one high-priority legal issue;
- step 1 uses the existing governed Assistant on that focused issue;
- if the Assistant supplies one NEXT_INVESTIGATION marker, step 2 runs it automatically;
- no task, chronology, evidence, report or Current Assessment mutation is performed.
"""

from __future__ import annotations

from collections.abc import Callable
import re
from typing import Any

import streamlit as st

from authentication import current_user_identity
from case_management import CaseRepository
from case_management.access import MatterMutationError
from document_manager import get_documents
from evidence_reference_bridge import ask_with_reference_findings
from governed_analytical_authority.models import GovernedRuntimeAnalyticalAuthority
from governed_analytical_authority.provider import (
    GovernedAnalyticalAuthorityProviderError,
    load_active_governed_analytical_authority,
)
from legal_issue_dashboard import LegalIssueDashboardError, build_legal_issue_dashboard
from solicitor_tasks import (
    SolicitorTaskError,
    TaskOrigin,
    TaskPriority,
    TaskStatus,
    create_task,
    load_tasks,
    update_task,
)
from task_work_progress import (
    TaskWorkOutcome,
    TaskWorkProgressError,
    append_task_work_progress,
    load_task_work_progress,
)


AuthorityLoader = Callable[[str], GovernedRuntimeAnalyticalAuthority | None]

_RESULT_KEY = "case_operator_last_result"
_RESULT_CASE_KEY = "case_operator_last_result_case_id"
_RESULT_QUESTION_KEY = "case_operator_last_question"
_TRACE_KEY = "case_operator_last_trace"
_PROPOSAL_DISMISSED_KEY = "case_operator_dismissed_task_proposal"
_PROPOSAL_CREATED_KEY = "case_operator_created_task_proposal"
_TASK_EXECUTION_CASE_KEY = "case_operator_task_execution_case_id"
_TASK_EXECUTION_TASK_KEY = "case_operator_task_execution_task_id"
_TASK_EXECUTION_RESULT_KEY = "case_operator_task_execution_result"
_TASK_EXECUTION_QUESTION_KEY = "case_operator_task_execution_question"

_STRONG_STATUSES = {"well_supported", "established", "supported"}

_GATEWAY_TERMS = (
    "limitation",
    "time limit",
    "jurisdiction",
    "preliminary",
    "strike out",
    "deposit order",
    "admissibility",
    "estoppel",
)

_URGENT_TERMS = (
    "dismissal",
    "termination",
    "capability",
    "hearing",
    "deadline",
    "injunction",
)

_NEXT_RE = re.compile(
    r"(?im)^[ \t]*(?:\[[a-z0-9_ -]+\][ \t]*)?NEXT_INVESTIGATION:[ \t]*(.+?)[ \t]*$"
)
_STATUS_PREFIX_RE = re.compile(
    r"(?im)^[ \t]*\[(?:supported_but_not_established|unresolved|supported|established|"
    r"well_supported|partially_supported|insufficiently_evidenced)\][ \t]*"
)


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def _clean_open_point(value: object) -> str:
    text = _clean(value)
    # Working-view cleanup only. Frozen analytical text is not mutated.
    return re.sub(
        r"^[\s?\uFFFD\u2753\u2022\u00B7\u2013\u2014\-]+",
        "",
        text,
    ).strip()


def _status_token(value: object) -> str:
    return _clean(value).lower().replace(" ", "_").replace("-", "_")


def _iter_text(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = _clean_open_point(value)
        return (text,) if text else ()
    try:
        values = tuple(value)
    except TypeError:
        text = _clean_open_point(value)
        return (text,) if text else ()

    result: list[str] = []
    for item in values:
        text = _clean_open_point(item)
        if text:
            result.append(text)
    return tuple(result)


def _element_open_points(element: Any) -> tuple[str, ...]:
    points: list[str] = []
    for attr in ("unresolved_matters", "evidential_gaps"):
        for item in _iter_text(getattr(element, attr, ())):
            if item not in points:
                points.append(item)

    status = _status_token(getattr(element, "provisional_status", ""))
    if status and status not in _STRONG_STATUSES:
        question = _clean_open_point(
            getattr(element, "question", "")
            or getattr(element, "legal_question", "")
            or getattr(element, "element_question", "")
            or getattr(element, "element_name", "")
        )
        status_text = status.replace("_", " ")
        point = (
            f"{question} ? current position: {status_text}"
            if question
            else f"Current position: {status_text}"
        )
        if point not in points:
            points.append(point)

    return tuple(points)


def issue_attention_points(issue: Any) -> tuple[str, ...]:
    """Return solicitor-facing open points without reclassifying frozen evidence."""
    points: list[str] = []
    for element in tuple(getattr(issue, "elements", ()) or ()):
        for point in _element_open_points(element):
            if point not in points:
                points.append(point)

    for item in _iter_text(getattr(issue, "overall_limitations", ())):
        if item not in points:
            points.append(item)

    return tuple(points)


def attention_issues(dashboard: Any) -> tuple[Any, ...]:
    """Preserve canonical issue order; this queue is not itself a merits ranking."""
    return tuple(
        issue
        for issue in tuple(getattr(dashboard, "issues", ()) or ())
        if issue_attention_points(issue)
    )


def opening_priority_score(issue: Any, ordinal: int) -> tuple[int, int, int]:
    """Deterministically prioritise gateway/urgent work before volume of open points."""
    name = _clean(getattr(issue, "issue_name", "")).lower()
    gateway = int(any(term in name for term in _GATEWAY_TERMS))
    urgent = int(any(term in name for term in _URGENT_TERMS))
    open_count = min(len(issue_attention_points(issue)), 99)
    return gateway, urgent, open_count - ordinal


def select_opening_issue(dashboard: Any) -> Any | None:
    """Select one attention-bearing issue without an LLM or evidence reclassification."""
    issues = attention_issues(dashboard)
    if not issues:
        issues = tuple(getattr(dashboard, "issues", ()) or ())
    if not issues:
        return None

    ranked = tuple(
        (opening_priority_score(issue, ordinal), issue)
        for ordinal, issue in enumerate(issues)
    )
    return max(ranked, key=lambda item: item[0])[1]


def opening_priority_reason(issue: Any) -> str:
    name = _clean(getattr(issue, "issue_name", "")).lower()
    if any(term in name for term in _GATEWAY_TERMS):
        return "procedural / gateway risk"
    if any(term in name for term in _URGENT_TERMS):
        return "current or time-sensitive legal work"
    return "largest unresolved attention burden in the current assessment"


def build_operator_review_question(dashboard: Any) -> str:
    """Compatibility helper: return the focused R5 opening question."""
    issue = select_opening_issue(dashboard)
    if issue is None:
        return (
            "Review the active matter and identify one focused legal issue requiring attention. "
            "Use governed evidence and do not change the Current Assessment."
        )
    return build_issue_investigation_question(issue, autonomous=True)


def build_issue_investigation_question(issue: Any, *, autonomous: bool = False) -> str:
    """Build a focused first-step question that avoids broad source-comparison routing."""
    name = _clean(getattr(issue, "issue_name", "") or "Legal issue")
    next_instruction = (
        '\nEnd with one line in exactly this form:\n'
        'NEXT_INVESTIGATION: <one focused investigation question>\n'
        'The line must contain one question only and no citation.'
        if autonomous
        else ""
    )

    return f"""Act as the claimant's LegalRAG Pro Case Operator.

Investigate this single legal issue:

ISSUE
{name}

Use the governed matter evidence available to the Assistant. Keep this first-step
review concise: normally no more than 700 words.

Address:
1. the precise factual propositions that presently need resolution;
2. the strongest contemporaneous primary evidence supporting the claimant;
3. the strongest evidence that weakens or qualifies the claimant's position;
4. the respondent's pleaded or later position where relevant;
5. what is documented fact, allegation, recollection, inference or unknown;
6. the practical legal significance, expressed conservatively;
7. what single focused investigation should happen next.

Separate CACI employer action from Unum/insurer action where relevant.
Distinguish recommendation, proposal, agreement and actual implementation.
Cite material source documents and pages.
Do not make a corpus-wide absence claim from a partial semantic search.
Do not silently change the Current Assessment.
If a material new point emerges, identify it as provisional and requiring review.
{next_instruction}""".strip()


def extract_next_investigation(answer: object) -> str | None:
    if not isinstance(answer, str):
        return None
    matches = _NEXT_RE.findall(answer)
    if len(matches) != 1:
        return None
    value = _clean(matches[0])
    return value or None


def build_follow_up_question(issue: Any, next_investigation: str) -> str:
    """Run exactly the investigation selected by step 1; comparison routing is allowed here."""
    name = _clean(getattr(issue, "issue_name", "") or "Legal issue")
    question = _clean(next_investigation)
    return f"""Act as the claimant's LegalRAG Pro Case Operator.

The first focused review selected this next investigation:

{question}

Related legal issue: {name}

Carry out that investigation now using the governed matter evidence.
Keep the solicitor-facing answer focused and normally under 1,200 words.
Cite material source documents and pages. State important evidence that helps,
weakens or qualifies the claimant's position. Distinguish CACI action from
Unum/insurer action where relevant. Distinguish proposal or recommendation from
actual implementation. Do not silently change the Current Assessment. If the
investigation produces a material new point, keep it provisional pending
professional review.

End with:
WHAT I FOUND
WHAT HELPS THE CASE
WHAT WEAKENS OR QUALIFIES IT
WHAT REMAINS UNKNOWN
RECOMMENDED NEXT ACTION
""".strip()


def extract_recommended_next_action(answer: object) -> str | None:
    """Extract the solicitor-facing recommended action from a validated answer."""
    text = _solicitor_answer_text(answer)
    if not text:
        return None

    match = re.search(
        r"(?ims)^\s*RECOMMENDED NEXT ACTION:\s*(.+?)"
        r"(?=^\s*Frozen analytical limitations:|\Z)",
        text,
    )
    if match is None:
        return None

    value = _clean(match.group(1))
    return value or None


def default_proposed_task_title(issue_name: object) -> str:
    """Return a short editable task prefill without making a new legal finding."""
    name = _clean(issue_name)
    token = name.lower()

    if "limitation" in token:
        return "Prepare limitation act/omission schedule"
    if "employer knowledge" in token:
        return "Verify employer knowledge evidence"
    if "reasonable adjustment" in token:
        return "Verify adjustment implementation evidence"
    if "discrimination arising" in token:
        return "Particularise disability-related treatment"
    return "Investigate " + (name or "priority legal issue")


def _default_task_priority(issue_name: object) -> TaskPriority:
    token = _clean(issue_name).lower()
    if any(term in token for term in _GATEWAY_TERMS + _URGENT_TERMS):
        return TaskPriority.HIGH
    return TaskPriority.MEDIUM


def _priority_label(priority: TaskPriority) -> str:
    return {
        TaskPriority.HIGH: "High",
        TaskPriority.MEDIUM: "Medium",
        TaskPriority.LOW: "Low",
        TaskPriority.NOT_SET: "Not set",
    }[priority]


def _priority_from_label(label: str) -> TaskPriority:
    return {
        "High": TaskPriority.HIGH,
        "Medium": TaskPriority.MEDIUM,
        "Low": TaskPriority.LOW,
        "Not set": TaskPriority.NOT_SET,
    }[label]


def _trace_issue_id(trace_item: dict[str, Any], issues: tuple[Any, ...]) -> str:
    direct = _clean(trace_item.get("issue_analysis_id"))
    if direct:
        return direct

    issue_name = _clean(trace_item.get("issue_name"))
    for issue in issues:
        if _clean(getattr(issue, "issue_name", "")) == issue_name:
            return _clean(getattr(issue, "issue_analysis_id", ""))
    return ""


def _proposal_fingerprint(
    case_id: str,
    issue_analysis_id: str,
    selected_investigation: str,
) -> str:
    return "::".join((case_id, issue_analysis_id, _clean(selected_investigation)))


def _render_proposed_task(
    *,
    case_id: str,
    trace: list[dict[str, Any]],
    issues: tuple[Any, ...],
) -> None:
    """Render an editable task proposal; persist only after explicit approval."""
    if len(trace) < 2:
        return

    final_step = trace[-1]
    if final_step.get("kind") != "next_investigation":
        return

    selected_investigation = _clean(final_step.get("selected_investigation"))
    issue_name = _clean(final_step.get("issue_name")) or "Legal issue"
    issue_analysis_id = _trace_issue_id(final_step, issues)
    result = final_step.get("result")
    answer = result.get("answer") if isinstance(result, dict) else None
    recommended = extract_recommended_next_action(answer)

    if not selected_investigation:
        return

    if not issue_analysis_id:
        st.warning(
            "The operator produced a proposed next action, but its legal-issue identity "
            "could not be resolved safely. No task can be created from this proposal."
        )
        return

    fingerprint = _proposal_fingerprint(
        case_id,
        issue_analysis_id,
        selected_investigation,
    )

    st.divider()
    st.subheader("Proposed next task")
    st.caption(
        "This is an editable work proposal derived from the completed Case Operator "
        "investigation. It is not a legal finding and nothing is saved unless you approve it."
    )

    if st.session_state.get(_PROPOSAL_CREATED_KEY) == fingerprint:
        st.success("Approved task created. It is now available in the matter task list.")
        if st.button(
            "Open matter tasks",
            key="case_operator_open_tasks_after_create",
            type="primary",
        ):
            st.session_state["mw1_task_workspace_case_id"] = case_id
            st.session_state.pop("case_operator_workspace_case_id", None)
            st.rerun()
        return

    if st.session_state.get(_PROPOSAL_DISMISSED_KEY) == fingerprint:
        st.info("This proposed task was dismissed. No task was created.")
        if st.button(
            "Restore proposal",
            key="case_operator_restore_task_proposal",
        ):
            st.session_state.pop(_PROPOSAL_DISMISSED_KEY, None)
            st.rerun()
        return

    default_priority = _default_task_priority(issue_name)
    priority_labels = ("High", "Medium", "Low", "Not set")
    priority_index = priority_labels.index(_priority_label(default_priority))

    why_default = recommended or (
        "Carry out the focused investigation selected by the Case Operator: "
        + selected_investigation
    )

    with st.form("case_operator_proposed_task_form", clear_on_submit=False):
        st.markdown("**Legal issue**")
        st.write(issue_name)

        title = st.text_input(
            "Task",
            value=default_proposed_task_title(issue_name),
        )
        priority_label = st.selectbox(
            "Priority",
            options=priority_labels,
            index=priority_index,
        )
        why_it_matters = st.text_area(
            "Why this matters / work to do",
            value=why_default,
            height=180,
        )

        st.markdown("**Originating investigation**")
        st.write(selected_investigation)

        left, right = st.columns(2)
        approve = left.form_submit_button(
            "Approve and create task",
            type="primary",
        )
        dismiss = right.form_submit_button("Dismiss proposal")

    if dismiss:
        st.session_state[_PROPOSAL_DISMISSED_KEY] = fingerprint
        st.session_state.pop(_PROPOSAL_CREATED_KEY, None)
        st.rerun()

    if not approve:
        return

    try:
        access = CaseRepository().require_access(
            current_user_identity(),
            case_id,
        )
        task = create_task(
            case_id=case_id,
            access=access,
            title=title,
            priority=_priority_from_label(priority_label),
            issue_analysis_id=issue_analysis_id,
            issue_name=issue_name,
            originating_question=selected_investigation,
            origin=TaskOrigin.NEXT_LEGAL_ACTION,
            why_it_matters=why_it_matters,
        )
    except (SolicitorTaskError, MatterMutationError) as exc:
        st.error(str(exc))
        return

    st.session_state[_PROPOSAL_CREATED_KEY] = fingerprint
    st.session_state.pop(_PROPOSAL_DISMISSED_KEY, None)
    st.success("Task created: " + task.title)
    st.rerun()

_TASK_OUTCOME_RE = re.compile(
    r"(?im)^[ \t]*(?:\[[a-z0-9_ -]+\][ \t]*)?"
    r"TASK_OUTCOME:[ \t]*(COMPLETE|CONTINUE|BLOCKED)[ \t]*$"
)


def extract_next_task_investigation(answer: object) -> str | None:
    """Read one durable next-task marker without mutating any matter state."""
    if not isinstance(answer, str):
        return None

    values: list[str] = []
    for raw_line in answer.splitlines():
        line = raw_line.strip()
        if line.startswith("[") and "]" in line:
            line = line.split("]", 1)[1].strip()
        if not line.upper().startswith("NEXT_TASK_INVESTIGATION:"):
            continue
        value = line.split(":", 1)[1].strip()
        if value:
            values.append(value)

    if len(values) != 1:
        return None
    return values[0]

def build_task_continuation_question(
    task: Any,
    prior_progress: tuple[Any, ...],
) -> str:
    """Continue from the exact durable next investigation when one is available."""
    if not prior_progress:
        return build_task_execution_question(task)

    latest = prior_progress[-1]
    raw_previous_answer = getattr(latest, "answer", "")
    previous_answer = _clean(raw_previous_answer)
    previous_outcome = _clean(getattr(getattr(latest, "outcome", None), "value", ""))

    title = _clean(getattr(task, "title", "")) or "Approved matter task"
    issue_name = _clean(getattr(task, "issue_name", "")) or "Legal issue"
    why_it_matters = _clean(getattr(task, "why_it_matters", "")) or (
        "Complete the approved legal work accurately from the governed matter evidence."
    )

    prior = previous_answer[-6000:] if previous_answer else (
        "No previous answer text is available."
    )
    durable_next = extract_next_task_investigation(raw_previous_answer)

    if durable_next:
        next_instruction = f"""EXACT NEXT TASK INVESTIGATION
{durable_next}

Work that exact investigation now. Do not choose a different sub-investigation
unless the governed evidence shows that the stated investigation is impossible
to perform. If it is impossible, explain why and use TASK_OUTCOME: BLOCKED."""
    else:
        next_instruction = """No unique durable NEXT_TASK_INVESTIGATION marker exists in
the latest persisted result. For this transitional continuation only, identify
the single highest-value unresolved sub-investigation that can now be advanced
from the governed matter evidence, and work it now."""

    return f"""Act as the claimant's LegalRAG Pro Case Operator.

Continue this already-approved IN-PROGRESS matter task from its latest persisted
task-work result. Do not restart the task from zero and do not broaden it into a
general case review.

TASK
{title}

RELATED LEGAL ISSUE
{issue_name}

WHY THIS MATTERS / WORK TO DO
{why_it_matters}

LATEST PERSISTED TASK-WORK OUTCOME
{previous_outcome or "UNRESOLVED"}

LATEST PERSISTED TASK-WORK RESULT
{prior}

{next_instruction}

Do not merely repeat the previous result. State:
1. the sub-investigation worked and why it was the correct next step;
2. what additional work you completed;
3. the material documentary evidence found, with source/page citations;
4. important adverse or qualifying material;
5. what remains unproved, unavailable or ambiguous;
6. whether the approved task is now complete, should continue, or is blocked.

Distinguish CACI/employer action from Unum/insurer action where relevant.
Distinguish proposal, recommendation or discussion from actual implementation.
Distinguish documented fact, party allegation, later recollection, inference
and unknown. Do not infer corpus-wide absence from a partial semantic search.
Do not silently change the Current Assessment or task state.

If further work remains AND the next investigation can be performed now using the
currently available governed matter evidence, choose exactly one next focused
investigation and end with exactly these two final lines:
NEXT_TASK_INVESTIGATION: <one focused next investigation>
TASK_OUTCOME: CONTINUE

If the task is complete, end with exactly:
TASK_OUTCOME: COMPLETE

If the next required step cannot be performed from the current governed matter
evidence because it requires an external document, external action or material
that must first be obtained from the Tribunal, claimant/client legal file,
respondent, insurer, third party or another source outside the current matter
corpus, the task is BLOCKED, not CONTINUE. Do not repeat the same corpus search.
End with exactly these two final lines:
NEXT_TASK_INVESTIGATION: <one focused unblock requirement>
TASK_OUTCOME: BLOCKED
""".strip()

def _progress_outcome(answer: object) -> TaskWorkOutcome:
    value = extract_task_outcome(answer)
    if value is None:
        return TaskWorkOutcome.UNRESOLVED
    return TaskWorkOutcome(value)


_GOVERNED_ANALYTICAL_FAILURE_ANSWER = (
    "I could not validate the governed analytical constraint for this answer. "
    "No analytically governed answer has been presented."
)


def _analytical_failure_reason(result):
    """Return a safe reason when governed analytical validation failed closed."""
    validation_error = result.get("analytical_validation_error")
    if isinstance(validation_error, str) and validation_error.strip():
        return validation_error.strip()

    mode = result.get("analytical_authority_mode")
    if mode in {"invalid_analytical_output", "invalid_authority"}:
        return "Governed analytical validation failed closed."

    answer = result.get("answer")
    if isinstance(answer, str) and answer.strip() == _GOVERNED_ANALYTICAL_FAILURE_ANSWER:
        return "Governed analytical validation failed closed."

    return None


def _substantive_task_work_history(history):
    """Exclude known fail-closed analytical attempts from continuation context."""
    return tuple(
        entry
        for entry in history
        if _clean(getattr(entry, "answer", "")) != _GOVERNED_ANALYTICAL_FAILURE_ANSWER
    )


def _persist_task_work_result(
    *,
    case_id: str,
    task_id: str,
    question: str,
    result: dict[str, Any],
) -> bool:
    """Persist one explicit Case Operator task-work action without changing task status."""
    analytical_failure = _analytical_failure_reason(result)
    if analytical_failure is not None:
        st.error(
            "The governed analytical result failed validation. "
            "No new task work was recorded."
        )
        st.caption(
            "The approved task remains unchanged. "
            "The failed analytical attempt is not used as continuation progress."
        )
        return False

    answer = result.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        st.error(
            "The governed task investigation returned no persistable answer. "
            "Task work has not been recorded."
        )
        return False

    try:
        access = CaseRepository().require_access(
            current_user_identity(),
            case_id,
        )
        append_task_work_progress(
            case_id=case_id,
            access=access,
            task_id=task_id,
            question=question,
            answer=answer,
            outcome=_progress_outcome(answer),
        )
    except (TaskWorkProgressError, SolicitorTaskError, MatterMutationError) as exc:
        st.error("Task work could not be recorded: " + str(exc))
        return False

    return True


def _render_task_work_history(
    *,
    history: tuple[Any, ...],
) -> None:
    if not history:
        st.caption(
            "No durable Case Operator work has yet been recorded for this task."
        )
        return

    st.caption(
        f"Persisted Case Operator work: {len(history)} "
        + ("entry" if len(history) == 1 else "entries")
        + "."
    )
    with st.expander("Previous task work", expanded=False):
        for index, record in enumerate(reversed(history[-5:]), start=1):
            outcome = _clean(
                getattr(getattr(record, "outcome", None), "value", "UNRESOLVED")
            )
            recorded_at = _clean(getattr(record, "recorded_at", ""))
            st.markdown(
                "**"
                + ("Latest" if index == 1 else f"Earlier {index - 1}")
                + " - "
                + outcome
                + (" - " + recorded_at if recorded_at else "")
                + "**"
            )
            st.write(_clean(getattr(record, "answer", "")))

def build_task_execution_question(task: Any) -> str:
    """Build one focused governed investigation from an already-approved matter task."""
    title = _clean(getattr(task, "title", "")) or "Approved matter task"
    issue_name = _clean(getattr(task, "issue_name", "")) or "Legal issue"
    originating_question = _clean(
        getattr(task, "originating_question", "")
    ) or title
    why_it_matters = _clean(getattr(task, "why_it_matters", "")) or (
        "Complete the approved legal work accurately from the governed matter evidence."
    )
    status = _clean(getattr(getattr(task, "status", None), "value", "open"))

    return f"""Act as the claimant's LegalRAG Pro Case Operator.

Work this already-approved matter task. Do not broaden the task into a general
case review.

TASK
{title}

RELATED LEGAL ISSUE
{issue_name}

CURRENT TASK STATUS
{status}

ORIGINATING INVESTIGATION
{originating_question}

WHY THIS MATTERS / WORK TO DO
{why_it_matters}

Use the governed matter evidence available to the Assistant. Keep the result
focused and normally under 1,200 words.

Report:
1. what work you were able to complete;
2. the material documentary evidence found, with source/page citations;
3. important evidence or circumstances that qualify the apparent conclusion;
4. what remains unproved, unavailable or ambiguous;
5. whether the approved task is complete, should continue, or is blocked.

Distinguish CACI/employer action from Unum/insurer action where relevant.
Distinguish proposal, recommendation or discussion from actual implementation.
Distinguish documented fact, party allegation, later recollection, inference
and unknown. Do not infer corpus-wide absence from a partial semantic search.
Do not silently change the Current Assessment or task state.

If further work remains AND the next investigation can be performed now using the
currently available governed matter evidence, choose exactly one next focused
investigation and end with exactly these two final lines:
NEXT_TASK_INVESTIGATION: <one focused next investigation>
TASK_OUTCOME: CONTINUE

If the task is complete, end with exactly:
TASK_OUTCOME: COMPLETE

If the next required step cannot be performed from the current governed matter
evidence because it requires an external document, external action or material
that must first be obtained from the Tribunal, claimant/client legal file,
respondent, insurer, third party or another source outside the current matter
corpus, the task is BLOCKED, not CONTINUE. Do not repeat the same corpus search.
End with exactly these two final lines:
NEXT_TASK_INVESTIGATION: <one focused unblock requirement>
TASK_OUTCOME: BLOCKED
""".strip()


def extract_task_outcome(answer: object) -> str | None:
    """Read the advisory task outcome without mutating task state."""
    if not isinstance(answer, str):
        return None
    matches = _TASK_OUTCOME_RE.findall(answer)
    if len(matches) != 1:
        return None
    return matches[0].upper()


def _task_execution_key(case_id: str, task_id: str) -> str:
    return case_id + "::" + task_id


def _clear_task_execution_state() -> None:
    for key in (
        _TASK_EXECUTION_TASK_KEY,
        _TASK_EXECUTION_RESULT_KEY,
        _TASK_EXECUTION_QUESTION_KEY,
        _TASK_EXECUTION_CASE_KEY,
    ):
        st.session_state.pop(key, None)


def _update_task_status(
    *,
    case_id: str,
    task_id: str,
    status: TaskStatus,
) -> None:
    """Use the existing append-only task service after an explicit UI decision."""
    access = CaseRepository().require_access(
        current_user_identity(),
        case_id,
    )
    update_task(
        case_id=case_id,
        access=access,
        task_id=task_id,
        status=status,
    )


def _render_task_execution_result(
    *,
    case_id: str,
    tasks: tuple[Any, ...],
) -> None:
    stored_case = st.session_state.get(_TASK_EXECUTION_CASE_KEY)
    task_id = _clean(st.session_state.get(_TASK_EXECUTION_TASK_KEY))
    result = st.session_state.get(_TASK_EXECUTION_RESULT_KEY)

    if stored_case != case_id or not task_id or not isinstance(result, dict):
        return

    task = next(
        (
            item
            for item in tasks
            if _clean(getattr(item, "task_id", "")) == task_id
        ),
        None,
    )
    if task is None:
        st.warning(
            "The worked task is no longer available in the current matter task projection."
        )
        _clear_task_execution_state()
        return

    st.divider()
    st.subheader("Task work result")
    st.caption(
        "This is governed investigative work on an approved matter task. "
        "The task status has not been changed automatically."
    )
    st.markdown("**Task**")
    st.write(_clean(getattr(task, "title", "Task")))

    _render_result(result, heading="Case Operator task investigation")

    answer = result.get("answer")
    outcome = extract_task_outcome(answer)
    current_status = getattr(task, "status", None)

    st.markdown("**Operator recommendation**")
    if outcome == "COMPLETE":
        st.write("The investigation indicates that this task may be complete.")
    elif outcome == "CONTINUE":
        st.write("The investigation indicates that further work remains on this task.")
        next_task_investigation = extract_next_task_investigation(answer)
        if next_task_investigation:
            st.markdown("**Next task investigation**")
            st.write(next_task_investigation)
        else:
            st.caption(
                "No unique durable next-task marker was returned. The next continuation "
                "will select one transitional sub-investigation before deterministic "
                "continuation begins."
            )
    elif outcome == "BLOCKED":
        st.write("The investigation indicates that this task is presently blocked.")
    else:
        st.write(
            "No unique task-outcome marker was returned. The Case Operator will not "
            "suggest a status change."
        )

    left, middle, right = st.columns(3)

    if outcome == "COMPLETE" and current_status is not TaskStatus.COMPLETED:
        if left.button(
            "Approve completion",
            key="case_operator_approve_task_completion",
            type="primary",
        ):
            try:
                _update_task_status(
                    case_id=case_id,
                    task_id=task_id,
                    status=TaskStatus.COMPLETED,
                )
            except (SolicitorTaskError, MatterMutationError) as exc:
                st.error(str(exc))
            else:
                st.success("Task marked completed.")
                _clear_task_execution_state()
                st.rerun()

    if (
        outcome in {"CONTINUE", "BLOCKED"}
        and current_status is TaskStatus.OPEN
    ):
        if middle.button(
            "Mark in progress",
            key="case_operator_mark_task_in_progress",
        ):
            try:
                _update_task_status(
                    case_id=case_id,
                    task_id=task_id,
                    status=TaskStatus.IN_PROGRESS,
                )
            except (SolicitorTaskError, MatterMutationError) as exc:
                st.error(str(exc))
            else:
                st.success("Task marked in progress.")
                st.rerun()

    if right.button(
        "Open matter tasks",
        key="case_operator_open_tasks_from_execution",
    ):
        st.session_state["mw1_task_workspace_case_id"] = case_id
        st.session_state.pop("case_operator_workspace_case_id", None)
        st.rerun()


def _render_approved_task_execution(
    *,
    case_id: str,
    documents: list[str],
    open_tasks: tuple[Any, ...],
    all_tasks: tuple[Any, ...],
) -> None:
    st.divider()
    st.subheader("Work an approved task")
    st.caption(
        "Run governed work from an existing matter task. Each explicit work action is "
        "recorded in separate append-only task-work history; task status and the Current "
        "Assessment remain unchanged unless you separately approve a status change."
    )

    if not open_tasks:
        st.info("There are no open or in-progress matter tasks to work.")
        _render_task_execution_result(case_id=case_id, tasks=all_tasks)
        return

    task_by_id = {
        _clean(getattr(task, "task_id", "")): task
        for task in open_tasks
        if _clean(getattr(task, "task_id", ""))
    }
    task_ids = tuple(task_by_id)

    selected_task_id = st.selectbox(
        "Approved task",
        options=task_ids,
        format_func=lambda value: (
            _clean(getattr(task_by_id[value], "title", "Task"))
            + " - "
            + _clean(
                getattr(
                    getattr(task_by_id[value], "status", None),
                    "value",
                    "open",
                )
            ).replace("_", " ")
        ),
        key="case_operator_approved_task",
    )

    selected_task = task_by_id[selected_task_id]
    st.markdown("**Related issue**")
    st.write(_clean(getattr(selected_task, "issue_name", "Legal issue")))
    st.markdown("**Why this matters / work to do**")
    st.write(_clean(getattr(selected_task, "why_it_matters", "")))
    st.markdown("**Originating investigation**")
    st.write(_clean(getattr(selected_task, "originating_question", "")))

    try:
        history = load_task_work_progress(case_id, selected_task_id)
    except TaskWorkProgressError as exc:
        st.error("Persisted task-work history could not be validated: " + str(exc))
        return

    _render_task_work_history(history=history)

    substantive_history = _substantive_task_work_history(history)
    latest_substantive_outcome = (
        extract_task_outcome(getattr(substantive_history[-1], "answer", ""))
        if substantive_history
        else None
    )
    blocked = (
        selected_task.status is TaskStatus.IN_PROGRESS
        and latest_substantive_outcome == "BLOCKED"
    )
    continuing = (
        selected_task.status is TaskStatus.IN_PROGRESS
        and bool(substantive_history)
    )

    if blocked:
        st.warning(
            "Latest task work is blocked pending material or action outside the "
            "current matter evidence."
        )
        unblock_requirement = extract_next_task_investigation(
            getattr(substantive_history[-1], "answer", "")
        )
        if unblock_requirement:
            st.markdown("**Unblock requirement**")
            st.write(unblock_requirement)
        st.caption(
            "Retry only after the dependency has been satisfied or new relevant "
            "matter material has been added."
        )

    button_label = (
        "Retry blocked task"
        if blocked
        else ("Continue selected task" if continuing else "Work selected task")
    )

    if st.button(
        button_label,
        key="case_operator_work_selected_task",
        type="primary",
    ):
        question = (
            build_task_continuation_question(selected_task, _substantive_task_work_history(history))
            if continuing
            else build_task_execution_question(selected_task)
        )
        try:
            result = _run_question(case_id, documents, question)
        except Exception as exc:
            from openai import APITimeoutError, RateLimitError

            if isinstance(exc, APITimeoutError):
                st.error(
                    "The AI provider did not return this task investigation within "
                    "the allowed time. No new task work was recorded."
                )
                st.caption(
                    "The approved task remains unchanged. You can retry the same "
                    "investigation later."
                )
                return

            if isinstance(exc, RateLimitError):
                detail = str(exc).lower()
                quota_exhausted = any(
                    marker in detail
                    for marker in (
                        "insufficient_quota",
                        "credit_balance_exhausted",
                        "no credits remaining",
                    )
                )
                if quota_exhausted:
                    st.error(
                        "The AI provider reports that API credit is unavailable. "
                        "No new task work was recorded."
                    )
                    st.caption(
                        "The approved task remains unchanged. Restore API credit "
                        "before retrying this investigation."
                    )
                else:
                    st.error(
                        "The AI provider is temporarily rate limiting this request. "
                        "No new task work was recorded."
                    )
                    st.caption(
                        "The approved task remains unchanged. Retry this investigation "
                        "later."
                    )
                return

            raise

        st.session_state[_TASK_EXECUTION_CASE_KEY] = case_id
        st.session_state[_TASK_EXECUTION_TASK_KEY] = selected_task_id
        st.session_state[_TASK_EXECUTION_QUESTION_KEY] = question
        st.session_state[_TASK_EXECUTION_RESULT_KEY] = result

        if _persist_task_work_result(
            case_id=case_id,
            task_id=selected_task_id,
            question=question,
            result=result,
        ):
            st.rerun()

    _render_task_execution_result(case_id=case_id, tasks=all_tasks)

def _reset_result_for_case(case_id: str) -> None:
    if st.session_state.get(_RESULT_CASE_KEY) != case_id:
        st.session_state.pop(_RESULT_KEY, None)
        st.session_state.pop(_RESULT_QUESTION_KEY, None)
        st.session_state.pop(_TRACE_KEY, None)
        st.session_state.pop(_PROPOSAL_DISMISSED_KEY, None)
        st.session_state.pop(_PROPOSAL_CREATED_KEY, None)
        _clear_task_execution_state()
        st.session_state[_RESULT_CASE_KEY] = case_id


def _source_labels(result: dict[str, Any]) -> tuple[str, ...]:
    sources = result.get("sources")
    if not isinstance(sources, list) or not sources:
        return ()

    seen: set[tuple[str, str]] = set()
    labels: list[str] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        file_name = _clean(source.get("file") or "Unknown document")
        page = _clean(source.get("page") or "?")
        key = file_name, page
        if key in seen:
            continue
        seen.add(key)
        labels.append(f"{file_name} ? p.{page}")
        if len(labels) >= 12:
            break
    return tuple(labels)


def _solicitor_answer_text(answer: object) -> str:
    """Hide governed status tokens from the working view without altering raw provider output."""
    if not isinstance(answer, str):
        return ""
    return _STATUS_PREFIX_RE.sub("", answer).strip()


def _render_result(result: dict[str, Any], *, heading: str = "Operator result") -> None:
    st.subheader(heading)
    answer = result.get("answer")
    display_answer = _solicitor_answer_text(answer)
    st.write(display_answer if display_answer else "No answer text returned.")

    if result.get("new_ai_finding"):
        st.warning(
            "New AI finding ? provisional only. It has not changed the Current Assessment "
            "and requires review before it is relied upon as part of the case position."
        )

    labels = _source_labels(result)
    if labels:
        with st.expander("Source/page references returned in this investigation", expanded=False):
            for label in labels:
                st.write("? " + label)
            st.caption(
                "Use Evidence / Sources & Provenance to inspect important source text before "
                "using a proposition in a witness statement, submission or correspondence."
            )


def _run_question(case_id: str, documents: list[str], question: str) -> dict[str, Any]:
    return ask_with_reference_findings(question, documents, case_id=case_id)


def _run_autonomous_opening(
    case_id: str,
    documents: list[str],
    dashboard: Any,
) -> None:
    issue = select_opening_issue(dashboard)
    if issue is None:
        st.error("No legal issue is available for autonomous review.")
        return

    issue_name = _clean(getattr(issue, "issue_name", "") or "Legal issue")
    issue_analysis_id = _clean(getattr(issue, "issue_analysis_id", ""))
    st.session_state.pop(_PROPOSAL_DISMISSED_KEY, None)
    st.session_state.pop(_PROPOSAL_CREATED_KEY, None)
    status = st.status(
        f"Case Operator - step 1 of 2 - {issue_name}",
        expanded=True,
    )
    status.write(
        "Priority selected deterministically from the Current Assessment: "
        + opening_priority_reason(issue)
        + "."
    )

    first_question = build_issue_investigation_question(issue, autonomous=True)
    first = _run_question(case_id, documents, first_question)
    status.write("Step 1 complete. Reading the selected next investigation.")

    answer = first.get("answer") if isinstance(first, dict) else None
    next_investigation = extract_next_investigation(answer)

    trace: list[dict[str, Any]] = [
        {
            "kind": "focused_issue_review",
            "issue_name": issue_name,
            "issue_analysis_id": issue_analysis_id,
            "question": first_question,
            "result": first,
        }
    ]

    if not next_investigation:
        status.update(
            label="Case Operator stopped after step 1 - no unique NEXT_INVESTIGATION marker returned",
            state="complete",
            expanded=False,
        )
        st.session_state[_TRACE_KEY] = trace
        st.session_state[_RESULT_KEY] = first
        st.session_state[_RESULT_QUESTION_KEY] = first_question
        st.session_state[_RESULT_CASE_KEY] = case_id
        return

    status.update(
        label=f"Case Operator - step 2 of 2 - {next_investigation[:90]}",
        state="running",
        expanded=True,
    )
    second_question = build_follow_up_question(issue, next_investigation)
    second = _run_question(case_id, documents, second_question)
    status.write("Step 2 complete.")
    status.update(
        label="Case Operator autonomous opening review complete",
        state="complete",
        expanded=False,
    )

    trace.append(
        {
            "kind": "next_investigation",
            "issue_name": issue_name,
            "issue_analysis_id": issue_analysis_id,
            "question": second_question,
            "selected_investigation": next_investigation,
            "result": second,
        }
    )
    st.session_state[_TRACE_KEY] = trace
    st.session_state[_RESULT_KEY] = second
    st.session_state[_RESULT_QUESTION_KEY] = second_question
    st.session_state[_RESULT_CASE_KEY] = case_id


def show_case_operator(
    case_id: str | None,
    *,
    authority_loader: AuthorityLoader = load_active_governed_analytical_authority,
) -> None:
    """Render R5 native Case Operator using existing governed services."""
    if st.button("Back to Legal Issues", key="case_operator_back"):
        st.session_state.pop("case_operator_workspace_case_id", None)
        st.rerun()

    st.title("Case Operator")
    st.caption(
        "AI-assisted case work over the existing governed matter. The operator may "
        "orient, investigate and propose next work, but it does not alter analytical "
        "authority, evidence, chronology or tasks."
    )

    if case_id is None or not str(case_id).strip():
        st.info("Select an active matter to use Case Operator.")
        return

    _reset_result_for_case(case_id)

    try:
        documents = list(get_documents(case_id))
    except Exception as exc:
        st.error("The indexed matter documents could not be loaded.")
        st.caption(type(exc).__name__)
        return

    if not documents:
        st.info("This matter has no selected indexed documents to investigate.")
        return

    try:
        authority = authority_loader(case_id)
    except GovernedAnalyticalAuthorityProviderError:
        st.error("The Current Assessment could not be validated. Case Operator has not run.")
        return

    if authority is None:
        st.info("No Current Assessment is available for this matter.")
        return

    try:
        dashboard = build_legal_issue_dashboard(active_case_id=case_id, authority=authority)
    except LegalIssueDashboardError:
        st.error("The Current Assessment could not be projected safely. Case Operator has not run.")
        return

    try:
        tasks = load_tasks(case_id)
    except SolicitorTaskError:
        tasks = ()

    open_tasks = tuple(
        task for task in tasks
        if getattr(task, "status", None) in {TaskStatus.OPEN, TaskStatus.IN_PROGRESS}
    )
    issues = tuple(getattr(dashboard, "issues", ()) or ())
    attention = attention_issues(dashboard)

    left, middle, right = st.columns(3)
    left.metric("Matter documents", len(documents))
    middle.metric("Legal issues", len(issues))
    right.metric("Open / in-progress tasks", len(open_tasks))

    _render_approved_task_execution(
        case_id=case_id,
        documents=documents,
        open_tasks=open_tasks,
        all_tasks=tuple(tasks),
    )

    st.subheader("Current attention queue")
    st.caption(
        "Read-only orientation from unresolved, disputed or limited parts of the Current "
        "Assessment. This preserves canonical case order and is not itself a merits ranking."
    )

    if not attention:
        st.info("No explicit unresolved/gap/limitation marker is present in the Current Assessment.")
    else:
        for issue in attention:
            with st.container(border=True):
                st.markdown("**" + _clean(getattr(issue, "issue_name", "Legal issue")) + "**")
                points = issue_attention_points(issue)
                for point in points[:3]:
                    st.write("- " + point)
                if len(points) > 3:
                    st.caption(f"{len(points) - 3} further open point(s)")

    selected = select_opening_issue(dashboard)
    st.divider()
    st.subheader("Autonomous opening review")
    if selected is None:
        st.info("No legal issue is available for autonomous review.")
    else:
        selected_name = _clean(getattr(selected, "issue_name", "") or "Legal issue")
        st.write("**First issue selected:** " + selected_name)
        st.caption("Selection basis: " + opening_priority_reason(selected) + ".")
        st.write(
            "One click now performs a focused issue review, reads the single next "
            "investigation chosen by that review, and runs that investigation automatically."
        )

        if st.button(
            "Run autonomous opening review",
            type="primary",
            key="case_operator_run_opening",
        ):
            _run_autonomous_opening(case_id, documents, dashboard)
            st.rerun()

    if issues:
        st.subheader("Investigate one issue manually")
        issue_by_id = {
            str(getattr(issue, "issue_analysis_id", index)): issue
            for index, issue in enumerate(issues)
        }
        selected_id = st.selectbox(
            "Legal issue",
            options=tuple(issue_by_id),
            format_func=lambda value: _clean(
                getattr(issue_by_id[value], "issue_name", "Legal issue")
            ),
            key="case_operator_issue",
        )
        if st.button("Run issue investigation", key="case_operator_run_issue"):
            question = build_issue_investigation_question(issue_by_id[selected_id])
            result = _run_question(case_id, documents, question)
            st.session_state[_TRACE_KEY] = [
                {
                    "kind": "manual_issue_review",
                    "issue_name": _clean(
                        getattr(issue_by_id[selected_id], "issue_name", "Legal issue")
                    ),
                    "question": question,
                    "result": result,
                }
            ]
            st.session_state[_RESULT_KEY] = result
            st.session_state[_RESULT_QUESTION_KEY] = question
            st.session_state[_RESULT_CASE_KEY] = case_id
            st.rerun()

    trace = st.session_state.get(_TRACE_KEY)
    if isinstance(trace, list) and trace:
        st.divider()
        if len(trace) == 1:
            result = trace[0].get("result")
            if isinstance(result, dict):
                _render_result(result)
        else:
            first = trace[0].get("result")
            second = trace[-1].get("result")
            selected_investigation = _clean(
                trace[-1].get("selected_investigation", "")
            )

            if isinstance(first, dict):
                with st.expander("Step 1 - focused issue review", expanded=False):
                    _render_result(first, heading="Focused issue review")

            if selected_investigation:
                st.subheader("Investigation chosen by the operator")
                st.write(selected_investigation)

            if isinstance(second, dict):
                _render_result(second, heading="Focused investigation result")

            _render_proposed_task(
                case_id=case_id,
                trace=trace,
                issues=issues,
            )

    if open_tasks:
        with st.expander(f"Existing matter tasks ({len(open_tasks)})", expanded=False):
            for task in open_tasks:
                st.write(
                    "- "
                    + _clean(getattr(task, "title", "Task"))
                    + " - "
                    + _clean(getattr(getattr(task, "status", None), "value", "open"))
                )

    st.info(
        "Case Operator does not create tasks automatically and does not change the "
        "Current Assessment. A proposed task is saved only after you explicitly approve it."
    )


__all__ = [
    "attention_issues",
    "build_follow_up_question",
    "build_issue_investigation_question",
    "build_operator_review_question",
    "build_task_execution_question",
    "build_task_continuation_question",
    "extract_next_investigation",
    "extract_task_outcome",
    "extract_next_task_investigation",
    "extract_recommended_next_action",
    "default_proposed_task_title",
    "issue_attention_points",
    "opening_priority_reason",
    "opening_priority_score",
    "select_opening_issue",
    "show_case_operator",
]
