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
from case_management import CaseRepository, MatterAccessError
from case_management.access import MatterMutationError
from document_manager import get_documents
from evidence_reference_bridge import ask_with_reference_findings
from drafting_working_draft import (
    DraftingWorkingDraftError,
    load_working_draft,
    load_working_drafts,
)

from drafting_approved_work_product import (
    DraftingApprovedWorkProductError,
    load_approved_working_draft_products,
)
from drafting_working_draft_generation import (
    DraftingWorkingDraftGenerationError,
    generate_working_draft_candidate,
)
from drafting_working_draft_orchestration import (
    DraftingWorkingDraftOrchestrationError,
    PreparedWorkingDraft,
    prepare_generated_working_draft,
    record_prepared_working_draft,
)
from drafting_working_draft_release_orchestration import (
    WorkingDraftProfessionalReleaseError,
    prepare_working_draft_professional_release,
    record_working_draft_professional_release,
)
from work_product_release import WorkProductReleaseDecision
from legalrag import (
    INTERACTIVE_CHAT_MODEL,
    INTERACTIVE_REASONING_EFFORT,
    _legal_answer_provider_client,
)
from task_work_authority_scope import (
    load_task_work_authority_scope,
)
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
from task_work_retrieval_receipt import (
    TaskWorkRetrievalReceiptError,
    append_task_work_retrieval_receipt,
    load_task_work_retrieval_receipts,
)
from task_work_authority_scope import (
    TaskWorkAuthorityScopeError,
    load_task_work_authority_scopes,
    record_task_work_authority_scope,
    resolve_task_work_authority_scope,
)

AuthorityLoader = Callable[[str], GovernedRuntimeAnalyticalAuthority | None]

_RESULT_KEY = "case_operator_last_result"
_RESULT_CASE_KEY = "case_operator_last_result_case_id"
_RESULT_QUESTION_KEY = "case_operator_last_question"
_TRACE_KEY = "case_operator_last_trace"
_PROPOSAL_DISMISSED_KEY = "case_operator_dismissed_task_proposal"
_PROPOSAL_CREATED_KEY = "case_operator_created_task_proposal"
_TASK_POST_BLOCK_HANDOFF_KEY = "case_operator_post_block_handoff_task_id"
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
        progress = append_task_work_progress(
            case_id=case_id,
            access=access,
            task_id=task_id,
            question=question,
            answer=answer,
            outcome=_progress_outcome(answer),
        )
        try:
            append_task_work_retrieval_receipt(
                case_id=case_id,
                task_id=task_id,
                progress_id=progress.progress_id,
                task_work_recorded_at=progress.recorded_at,
                question=question,
                answer=answer,
                result=result,
            )
        except TaskWorkRetrievalReceiptError as exc:
            st.warning(
                "Task work was recorded, but its diagnostic retrieval receipt "
                "could not be recorded: " + str(exc)
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



_TASK_PRIORITY_ORDER = {
    "high": 0,
    "medium": 1,
    "low": 2,
    "not_set": 3,
}


def _task_priority_order(task: Any) -> int:
    priority = getattr(task, "priority", None)
    value = getattr(priority, "value", priority)
    normalized = _clean(value).lower()
    return _TASK_PRIORITY_ORDER.get(normalized, 99)



def _post_block_handoff_target(
    *,
    handoff_from_task_id: str,
    current_selected_task_id: str,
    ready_tasks: tuple[Any, ...],
) -> str | None:
    """Return one READY handoff target only for a just-blocked selected task."""
    handoff_from = _clean(handoff_from_task_id)
    current_selected = _clean(current_selected_task_id)

    if not handoff_from:
        return None

    if current_selected != handoff_from:
        return None

    if not ready_tasks:
        return None

    target_task_id = _clean(
        getattr(ready_tasks[0], "task_id", "")
    )

    if not target_task_id:
        return None

    if target_task_id == handoff_from:
        return None

    return target_task_id


def _project_approved_task_queue(
    *,
    case_id: str,
    open_tasks: tuple[Any, ...],
) -> tuple[tuple[Any, ...], tuple[Any, ...], tuple[Any, ...]]:
    """Project READY/BLOCKED approved tasks without mutating task state."""
    ready: list[tuple[int, int, Any]] = []
    blocked: list[tuple[int, int, Any]] = []
    unavailable: list[tuple[int, Any]] = []

    for canonical_index, task in enumerate(open_tasks):
        status = getattr(task, "status", None)
        if status not in {TaskStatus.OPEN, TaskStatus.IN_PROGRESS}:
            continue

        task_id = _clean(getattr(task, "task_id", ""))
        if not task_id:
            unavailable.append((canonical_index, task))
            continue

        try:
            history = load_task_work_progress(case_id, task_id)
        except TaskWorkProgressError:
            unavailable.append((canonical_index, task))
            continue

        substantive = _substantive_task_work_history(history)
        latest_outcome = (
            extract_task_outcome(getattr(substantive[-1], "answer", ""))
            if substantive
            else None
        )

        ranked = (
            _task_priority_order(task),
            canonical_index,
            task,
        )

        if latest_outcome == "BLOCKED":
            blocked.append(ranked)
        else:
            ready.append(ranked)

    ready.sort(key=lambda item: (item[0], item[1]))
    blocked.sort(key=lambda item: (item[0], item[1]))
    unavailable.sort(key=lambda item: item[0])

    return (
        tuple(item[2] for item in ready),
        tuple(item[2] for item in blocked),
        tuple(item[1] for item in unavailable),
    )



def _task_work_scope_progress_id(
    value: object,
    *,
    label: str,
) -> str:
    progress_id = str(
        getattr(
            value,
            "progress_id",
            "",
        )
    ).strip()

    if not progress_id:
        raise TaskWorkAuthorityScopeError(
            label + " has no progress_id."
        )

    return progress_id


def _task_work_scope_capture_rows(
    *,
    history: tuple[Any, ...],
    receipts: tuple[Any, ...],
    scopes: tuple[Any, ...],
) -> tuple[
    tuple[
        Any,
        Any,
        Any | None,
    ],
    ...,
]:
    """Join persisted work, R68 receipt and optional D1-I1 scope exactly."""

    progress_by_id: dict[
        str,
        Any,
    ] = {}

    ordered_progress_ids: list[
        str
    ] = []

    for progress in history:
        progress_id = (
            _task_work_scope_progress_id(
                progress,
                label="task-work record",
            )
        )

        if progress_id in progress_by_id:
            raise TaskWorkAuthorityScopeError(
                "task-work history contains duplicate progress_id."
            )

        progress_by_id[
            progress_id
        ] = progress

        ordered_progress_ids.append(
            progress_id
        )

    receipt_by_id: dict[
        str,
        Any,
    ] = {}

    for receipt in receipts:
        progress_id = (
            _task_work_scope_progress_id(
                receipt,
                label="retrieval receipt",
            )
        )

        if progress_id in receipt_by_id:
            raise TaskWorkAuthorityScopeError(
                "more than one retrieval receipt exists for one progress_id."
            )

        if progress_id not in progress_by_id:
            raise TaskWorkAuthorityScopeError(
                "retrieval receipt has no matching persisted task-work record."
            )

        receipt_by_id[
            progress_id
        ] = receipt

    scope_by_id: dict[
        str,
        Any,
    ] = {}

    for scope in scopes:
        progress_id = (
            _task_work_scope_progress_id(
                scope,
                label="authority-scope record",
            )
        )

        if progress_id in scope_by_id:
            raise TaskWorkAuthorityScopeError(
                "more than one authority scope exists for one progress_id."
            )

        if progress_id not in progress_by_id:
            raise TaskWorkAuthorityScopeError(
                "authority scope has no matching persisted task-work record."
            )

        if progress_id not in receipt_by_id:
            raise TaskWorkAuthorityScopeError(
                "authority scope has no matching R68 retrieval receipt."
            )

        scope_by_id[
            progress_id
        ] = scope

    return tuple(
        (
            progress_by_id[
                progress_id
            ],
            receipt_by_id[
                progress_id
            ],
            scope_by_id.get(
                progress_id
            ),
        )
        for progress_id
        in ordered_progress_ids
        if progress_id
        in receipt_by_id
    )


def _task_work_scope_issue_elements(
    *,
    authority: object,
    task: object,
) -> tuple[
    object,
    tuple[Any, ...],
]:
    """Resolve only the current governed issue explicitly bound to the task."""

    issue_analysis_id = str(
        getattr(
            task,
            "issue_analysis_id",
            "",
        )
    ).strip()

    if not issue_analysis_id:
        raise TaskWorkAuthorityScopeError(
            "task has no governed issue binding."
        )

    try:
        issue_matrix = tuple(
            authority
            .case_matrices
            .issue_matrix
        )
    except (
        AttributeError,
        TypeError,
    ) as exc:
        raise TaskWorkAuthorityScopeError(
            "current governed authority does not expose the issue matrix."
        ) from exc

    matches = tuple(
        issue
        for issue in issue_matrix
        if str(
            getattr(
                issue,
                "issue_analysis_id",
                "",
            )
        ).strip()
        == issue_analysis_id
    )

    if len(matches) != 1:
        raise TaskWorkAuthorityScopeError(
            "task issue is not uniquely present in the current governed authority."
        )

    issue = matches[0]

    try:
        elements = tuple(
            issue.element_records
        )
    except (
        AttributeError,
        TypeError,
    ) as exc:
        raise TaskWorkAuthorityScopeError(
            "current governed issue does not expose focus areas."
        ) from exc

    if not elements:
        raise TaskWorkAuthorityScopeError(
            "current governed issue contains no focus areas."
        )

    element_ids = tuple(
        str(
            getattr(
                element,
                "element_id",
                "",
            )
        ).strip()
        for element in elements
    )

    if any(
        not element_id
        for element_id in element_ids
    ):
        raise TaskWorkAuthorityScopeError(
            "current governed issue contains an invalid focus-area identity."
        )

    if len(
        element_ids
    ) != len(
        set(
            element_ids
        )
    ):
        raise TaskWorkAuthorityScopeError(
            "current governed issue contains duplicate focus-area identities."
        )

    return (
        issue,
        elements,
    )


def _task_work_scope_element_label(
    element: object,
) -> str:
    name = str(
        getattr(
            element,
            "element_name",
            "",
        )
    ).strip()

    question = str(
        getattr(
            element,
            "legal_question",
            "",
        )
    ).strip()

    if name and question:
        return (
            name
            + " - "
            + question
        )

    if name:
        return name

    if question:
        return question

    return "Case assessment focus area"


def _current_scope_reviewer_reference() -> str:
    identity = current_user_identity()

    email = str(
        getattr(
            identity,
            "email",
            "",
        )
    ).strip()

    if not email:
        raise TaskWorkAuthorityScopeError(
            "the authenticated user has no canonical reviewer email."
        )

    return email


def _render_task_work_scope_capture(
    *,
    case_id: str,
    task: object,
    history: tuple[Any, ...],
) -> None:
    """Offer explicit professional scope only for exactly receipted work."""

    task_id = str(
        getattr(
            task,
            "task_id",
            "",
        )
    ).strip()

    if not task_id:
        st.error(
            "Work scope cannot be reviewed because the task identity is unavailable."
        )

        return

    try:
        receipts = (
            load_task_work_retrieval_receipts(
                case_id,
                task_id,
            )
        )

    except TaskWorkRetrievalReceiptError as exc:
        st.error(
            "Work scope cannot be reviewed because the task-work "
            "retrieval record could not be validated: "
            + str(exc)
        )

        return

    # Historical/unreceipted work is intentionally ineligible.
    # Do not load authority or create any scope UI for it.
    if not receipts:
        return

    try:
        scopes = (
            load_task_work_authority_scopes(
                case_id,
                task_id,
            )
        )

        rows = (
            _task_work_scope_capture_rows(
                history=tuple(
                    history
                ),
                receipts=tuple(
                    receipts
                ),
                scopes=tuple(
                    scopes
                ),
            )
        )

    except TaskWorkAuthorityScopeError as exc:
        st.error(
            "Persisted work scope could not be validated: "
            + str(exc)
        )

        return

    if not rows:
        return

    try:
        authority = (
            load_active_governed_analytical_authority(
                case_id
            )
        )

    except GovernedAnalyticalAuthorityProviderError as exc:
        st.error(
            "Work scope cannot be reviewed because the current "
            "case assessment could not be loaded: "
            + str(exc)
        )

        return

    if authority is None:
        st.error(
            "Work scope cannot be reviewed because there is no "
            "current governed case assessment."
        )

        return

    try:
        _, elements = (
            _task_work_scope_issue_elements(
                authority=authority,
                task=task,
            )
        )

    except TaskWorkAuthorityScopeError as exc:
        st.error(
            "Work scope cannot be reviewed: "
            + str(exc)
        )

        return

    element_by_id = {
        str(
            element.element_id
        ): element
        for element in elements
    }

    element_ids = tuple(
        element_by_id
    )

    st.markdown(
        "### Work scope"
    )

    st.caption(
        "For work that has a verified retrieval record, choose which "
        "parts of the current case assessment the work relates to. "
        "Nothing is selected automatically."
    )

    for (
        progress,
        receipt,
        existing_scope,
    ) in rows:
        progress_id = (
            _task_work_scope_progress_id(
                progress,
                label="task-work record",
            )
        )

        recorded_at = str(
            getattr(
                progress,
                "recorded_at",
                "",
            )
        ).strip()

        if existing_scope is not None:
            st.markdown(
                "**Work scope set"
                + (
                    " ? "
                    + recorded_at
                    if recorded_at
                    else ""
                )
                + "**"
            )

            try:
                resolution = (
                    resolve_task_work_authority_scope(
                        existing_scope,
                        authority=authority,
                    )
                )

            except TaskWorkAuthorityScopeError as exc:
                st.error(
                    "This existing work scope is no longer current "
                    "and will not be rewritten automatically: "
                    + str(exc)
                )

                continue

            labels = tuple(
                _task_work_scope_element_label(
                    element
                )
                for element
                in resolution.elements
            )

            for label in labels:
                st.write(
                    "? " + label
                )

            st.caption(
                "Set by "
                + existing_scope.reviewer_reference
                + " on "
                + existing_scope.recorded_at
                + "."
            )

            continue

        st.markdown(
            "**Set scope for work"
            + (
                " recorded "
                + recorded_at
                if recorded_at
                else ""
            )
            + "**"
        )

        form_key = (
            "case_operator_work_scope_"
            + task_id
            + "_"
            + progress_id
        )

        with st.form(
            key=form_key
        ):
            selected_element_ids = (
                st.multiselect(
                    "Relevant focus areas",
                    options=
                        element_ids,
                    default=(),
                    format_func=lambda element_id: (
                        _task_work_scope_element_label(
                            element_by_id[
                                element_id
                            ]
                        )
                    ),
                    key=(
                        form_key
                        + "_elements"
                    ),
                )
            )

            review_note = (
                st.text_area(
                    "Review note (optional)",
                    value="",
                    key=(
                        form_key
                        + "_note"
                    ),
                )
            )

            submitted = (
                st.form_submit_button(
                    "Set work scope"
                )
            )

        if not submitted:
            continue

        if not selected_element_ids:
            st.error(
                "Select at least one focus area before setting work scope."
            )

            continue

        try:
            # Re-load at the explicit decision point so a changed
            # authority cannot silently inherit the displayed scope.
            current_authority = (
                load_active_governed_analytical_authority(
                    case_id
                )
            )

            if current_authority is None:
                raise TaskWorkAuthorityScopeError(
                    "there is no current governed case assessment."
                )

            identity = (
                current_user_identity()
            )

            CaseRepository().require_access(
                identity,
                case_id,
            )

            reviewer_reference = str(
                getattr(
                    identity,
                    "email",
                    "",
                )
            ).strip()

            if not reviewer_reference:
                raise TaskWorkAuthorityScopeError(
                    "the authenticated user has no canonical reviewer email."
                )

            record_task_work_authority_scope(
                task=task,
                progress=progress,
                retrieval_receipt=
                    receipt,
                authority=
                    current_authority,
                element_ids=
                    tuple(
                        selected_element_ids
                    ),
                reviewer_reference=
                    reviewer_reference,
                review_note=
                    review_note,
            )

        except (
            TaskWorkAuthorityScopeError,
            GovernedAnalyticalAuthorityProviderError,
            MatterAccessError,
            MatterMutationError,
            PermissionError,
        ) as exc:
            st.error(
                "Work scope could not be recorded: "
                + str(exc)
            )

            continue

        st.success(
            "Work scope recorded."
        )

        st.rerun()


_DRAFTING_PREPARED_KEY = "case_operator_drafting_prepared"
_DRAFTING_CONTEXT_KEY = "case_operator_drafting_context"
_DRAFTING_SAVED_KEY = "case_operator_drafting_saved"
_DRAFTING_PROFESSIONAL_REVIEW_PREPARED_KEY = (
    "case_operator_drafting_professional_review_prepared"
)
_DRAFTING_PROFESSIONAL_REVIEW_CONTEXT_KEY = (
    "case_operator_drafting_professional_review_context"
)
_DRAFTING_PROFESSIONAL_REVIEW_RESULT_KEY = (
    "case_operator_drafting_professional_review_result"
)


class _DraftingUIError(RuntimeError):
    """A solicitor-facing Drafting action could not be bound safely."""


def _clear_drafting_state(
    *,
    preserve_saved: bool = False,
) -> None:
    st.session_state.pop(
        _DRAFTING_PREPARED_KEY,
        None,
    )
    st.session_state.pop(
        _DRAFTING_CONTEXT_KEY,
        None,
    )

    if not preserve_saved:
        st.session_state.pop(
            _DRAFTING_SAVED_KEY,
            None,
        )


def _drafting_context_matches(
    context: object,
    *,
    case_id: str,
    task_id: str,
    progress_id: str | None = None,
    scope_binding_id: str | None = None,
    element_id: str | None = None,
) -> bool:
    if not isinstance(
        context,
        dict,
    ):
        return False

    expected = {
        "case_id": case_id,
        "task_id": task_id,
    }

    if progress_id is not None:
        expected[
            "progress_id"
        ] = progress_id

    if scope_binding_id is not None:
        expected[
            "scope_binding_id"
        ] = scope_binding_id

    if element_id is not None:
        expected[
            "element_id"
        ] = element_id

    return all(
        str(
            context.get(
                key,
                "",
            )
        ).strip()
        == str(value).strip()
        for key, value
        in expected.items()
    )


def _drafting_check_presentation(
    result: object,
) -> tuple[str, str]:
    if hasattr(
        result,
        "value",
    ):
        result = getattr(
            result,
            "value",
        )

    value = str(
        result or ""
    ).strip().upper()

    if value == "ALIGNED":
        return (
            "success",
            "This wording is consistent with the current case assessment.",
        )

    if value == "CAUTION":
        return (
            "warning",
            "Review this wording carefully before saving. "
            "The current case assessment contains qualifications, "
            "unresolved points or evidence limitations relevant to it.",
        )

    if value == "NOT_AUTHORIZED":
        return (
            "error",
            "This wording goes beyond what the current case assessment "
            "presently supports. It may remain working material for "
            "professional review, but it is not approved for reliance.",
        )

    return (
        "error",
        "The wording check could not be interpreted safely. "
        "Do not rely on this proposed draft without further review.",
    )


def _professional_review_check_presentation(
    result: object,
) -> tuple[str, str]:
    kind, message = (
        _drafting_check_presentation(
            result
        )
    )

    if kind == "warning":
        message = message.replace(
            "Review this wording carefully before saving.",
            "Review this wording carefully before approving it for reliance.",
            1,
        )

    return (
        kind,
        message,
    )

def _load_drafting_action_context(
    *,
    case_id: str,
    task: object,
    progress_id: str,
    element_id: str,
) -> tuple[
    object,
    object,
    object,
    object,
    str,
]:
    task_id = _clean(
        getattr(
            task,
            "task_id",
            "",
        )
    )

    if not task_id:
        raise _DraftingUIError(
            "The selected task has no stable identity."
        )

    identity = (
        current_user_identity()
    )

    CaseRepository().require_access(
        identity,
        case_id,
    )

    creator_reference = _clean(
        getattr(
            identity,
            "email",
            "",
        )
    )

    if not creator_reference:
        raise _DraftingUIError(
            "The authenticated user has no canonical professional email."
        )

    progress_rows = tuple(
        load_task_work_progress(
            case_id,
            task_id,
        )
    )

    progress_matches = tuple(
        row
        for row in progress_rows
        if _clean(
            getattr(
                row,
                "progress_id",
                "",
            )
        )
        == progress_id
    )

    if len(
        progress_matches
    ) != 1:
        raise _DraftingUIError(
            "The selected recorded work is no longer uniquely available."
        )

    progress = progress_matches[0]

    receipts = tuple(
        load_task_work_retrieval_receipts(
            case_id,
            task_id,
        )
    )

    receipt_matches = tuple(
        receipt
        for receipt in receipts
        if _clean(
            getattr(
                receipt,
                "progress_id",
                "",
            )
        )
        == progress_id
    )

    if len(
        receipt_matches
    ) != 1:
        raise _DraftingUIError(
            "The selected recorded work no longer has one verified "
            "source record."
        )

    retrieval_receipt = (
        receipt_matches[0]
    )

    scope = (
        load_task_work_authority_scope(
            case_id,
            task_id,
            progress_id,
        )
    )

    if scope is None:
        raise _DraftingUIError(
            "The selected recorded work no longer has a professional "
            "work scope."
        )

    authority = (
        load_active_governed_analytical_authority(
            case_id
        )
    )

    if authority is None:
        raise _DraftingUIError(
            "No current case assessment is available."
        )

    resolution = (
        resolve_task_work_authority_scope(
            scope,
            authority=authority,
        )
    )

    element_matches = tuple(
        element
        for element in resolution.elements
        if _clean(
            getattr(
                element,
                "element_id",
                "",
            )
        )
        == element_id
    )

    if len(
        element_matches
    ) != 1:
        raise _DraftingUIError(
            "The selected draft focus is no longer available "
            "within the current work scope."
        )

    return (
        progress,
        retrieval_receipt,
        scope,
        authority,
        creator_reference,
    )


def _clear_drafting_professional_review_state(
    *,
    preserve_result: bool = False,
) -> None:
    st.session_state.pop(
        _DRAFTING_PROFESSIONAL_REVIEW_PREPARED_KEY,
        None,
    )
    st.session_state.pop(
        _DRAFTING_PROFESSIONAL_REVIEW_CONTEXT_KEY,
        None,
    )

    if not preserve_result:
        st.session_state.pop(
            _DRAFTING_PROFESSIONAL_REVIEW_RESULT_KEY,
            None,
        )


def _professional_review_context_matches(
    context: object,
    *,
    case_id: str,
    task_id: str,
    draft_id: str,
) -> bool:
    if not isinstance(
        context,
        dict,
    ):
        return False

    return (
        _clean(
            context.get(
                "case_id",
                "",
            )
        )
        == _clean(
            case_id
        )
        and _clean(
            context.get(
                "task_id",
                "",
            )
        )
        == _clean(
            task_id
        )
        and _clean(
            context.get(
                "draft_id",
                "",
            )
        )
        == _clean(
            draft_id
        )
    )


def _professional_review_result_value(
    evaluation: object,
) -> str:
    result = getattr(
        evaluation,
        "result",
        "",
    )

    if hasattr(
        result,
        "value",
    ):
        result = getattr(
            result,
            "value",
        )

    return _clean(
        result
    ).upper()


def _current_professional_reviewer_reference(
    *,
    case_id: str,
) -> str:
    identity = (
        current_user_identity()
    )

    CaseRepository().require_access(
        identity,
        case_id,
    )

    reviewer_reference = _clean(
        getattr(
            identity,
            "email",
            "",
        )
    )

    if not reviewer_reference:
        raise _DraftingUIError(
            "The authenticated user has no canonical professional email."
        )

    return reviewer_reference


def _load_exact_saved_working_draft(
    *,
    case_id: str,
    task_id: str,
    draft_id: str,
) -> object:
    draft = (
        load_working_draft(
            case_id,
            task_id,
            draft_id,
        )
    )

    if draft is None:
        raise _DraftingUIError(
            "The selected saved working draft is no longer available."
        )

    if _clean(
        getattr(
            draft,
            "draft_id",
            "",
        )
    ) != _clean(
        draft_id
    ):
        raise _DraftingUIError(
            "The selected saved working draft could not be resolved exactly."
        )

    return draft


def _working_draft_review_label(
    draft: object,
) -> str:
    title = (
        _clean(
            getattr(
                draft,
                "title",
                "",
            )
        )
        or "Working draft"
    )

    recorded_at = _clean(
        getattr(
            draft,
            "recorded_at",
            "",
        )
    )

    if recorded_at:
        return (
            title
            + " - saved "
            + recorded_at
        )

    return title


def _render_working_draft_professional_review(
    *,
    case_id: str,
    task_id: str,
    draft: object,
) -> None:
    draft_id = _clean(
        getattr(
            draft,
            "draft_id",
            "",
        )
    )

    if not draft_id:
        st.error(
            "This saved working draft has no stable identity and cannot be reviewed."
        )
        return

    stored_context = (
        st.session_state.get(
            _DRAFTING_PROFESSIONAL_REVIEW_CONTEXT_KEY
        )
    )

    if (
        stored_context is not None
        and not _professional_review_context_matches(
            stored_context,
            case_id=case_id,
            task_id=task_id,
            draft_id=draft_id,
        )
    ):
        _clear_drafting_professional_review_state()

    prepared_review = (
        st.session_state.get(
            _DRAFTING_PROFESSIONAL_REVIEW_PREPARED_KEY
        )
    )

    if prepared_review is not None:
        context = (
            st.session_state.get(
                _DRAFTING_PROFESSIONAL_REVIEW_CONTEXT_KEY
            )
        )

        target = getattr(
            prepared_review,
            "target",
            None,
        )

        target_id = _clean(
            getattr(
                target,
                "target_id",
                "",
            )
        )

        if (
            not _professional_review_context_matches(
                context,
                case_id=case_id,
                task_id=task_id,
                draft_id=draft_id,
            )
            or not target_id
            or target_id
            != _clean(
                context.get(
                    "target_id",
                    "",
                )
            )
        ):
            _clear_drafting_professional_review_state()
            prepared_review = None

    if prepared_review is None:
        st.caption(
            "Professional reliance is a separate decision from saving a working draft."
        )

        preview_clicked = (
            st.button(
                "Prepare professional review",
                key=(
                    "case_operator_prepare_professional_review_"
                    + case_id
                    + "_"
                    + task_id
                    + "_"
                    + draft_id
                ),
            )
        )

        if not preview_clicked:
            return

        try:
            _current_professional_reviewer_reference(
                case_id=case_id
            )

            fresh_draft = (
                _load_exact_saved_working_draft(
                    case_id=case_id,
                    task_id=task_id,
                    draft_id=draft_id,
                )
            )

            current_authority = (
                load_active_governed_analytical_authority(
                    case_id
                )
            )

            if current_authority is None:
                raise _DraftingUIError(
                    "No current case assessment is available."
                )

            prepared_review = (
                prepare_working_draft_professional_release(
                    draft=fresh_draft,
                    authority=current_authority,
                )
            )

            previewed_target_id = _clean(
                getattr(
                    getattr(
                        prepared_review,
                        "target",
                        None,
                    ),
                    "target_id",
                    "",
                )
            )

            if not previewed_target_id:
                raise _DraftingUIError(
                    "The professional review has no stable reviewed identity."
                )

        except (
            DraftingWorkingDraftError,
            GovernedAnalyticalAuthorityProviderError,
            MatterAccessError,
            MatterMutationError,
            WorkingDraftProfessionalReleaseError,
            _DraftingUIError,
            PermissionError,
        ) as exc:
            _clear_drafting_professional_review_state()
            st.error(
                "The professional review could not be prepared: "
                + str(exc)
            )
            return
        except Exception:
            _clear_drafting_professional_review_state()
            st.error(
                "The professional review could not be prepared safely. "
                "No professional decision has been made."
            )
            return

        st.session_state[
            _DRAFTING_PROFESSIONAL_REVIEW_PREPARED_KEY
        ] = prepared_review

        st.session_state[
            _DRAFTING_PROFESSIONAL_REVIEW_CONTEXT_KEY
        ] = {
            "case_id":
                case_id,
            "task_id":
                task_id,
            "draft_id":
                draft_id,
            "target_id":
                previewed_target_id,
        }

        st.rerun()
        return

    projection = getattr(
        prepared_review,
        "projection",
        None,
    )
    artifact = getattr(
        prepared_review,
        "artifact",
        None,
    )
    target = getattr(
        prepared_review,
        "target",
        None,
    )

    previewed_target_id = _clean(
        getattr(
            target,
            "target_id",
            "",
        )
    )

    statements = tuple(
        getattr(
            projection,
            "statements",
            (),
        )
    )
    evaluations = tuple(
        getattr(
            projection,
            "authority_evaluations",
            (),
        )
    )
    markdown = getattr(
        artifact,
        "markdown",
        None,
    )

    if (
        not previewed_target_id
        or not isinstance(
            markdown,
            str,
        )
        or not markdown
        or not statements
        or len(
            statements
        )
        != len(
            evaluations
        )
    ):
        _clear_drafting_professional_review_state()
        st.error(
            "The professional review snapshot is incomplete. Prepare it again."
        )
        return

    st.markdown(
        "#### Professional review"
    )
    st.caption(
        "Review the exact saved wording against the current case assessment "
        "before making a professional reliance decision."
    )

    for index, (
        statement,
        evaluation,
    ) in enumerate(
        zip(
            statements,
            evaluations,
            strict=True,
        ),
        start=1,
    ):
        sequence = getattr(
            statement,
            "sequence",
            index,
        )

        st.markdown(
            "**Statement "
            + str(
                sequence
            )
            + "**"
        )
        st.write(
            _clean(
                getattr(
                    statement,
                    "text",
                    "",
                )
            )
        )

        kind, message = (
            _professional_review_check_presentation(
                getattr(
                    evaluation,
                    "result",
                    "",
                )
            )
        )

        getattr(
            st,
            kind,
        )(
            message
        )

        reason = _clean(
            getattr(
                evaluation,
                "reason",
                "",
            )
        )

        if reason:
            st.caption(
                "Review note from the current case assessment: "
                + reason
            )

    with st.expander(
        "Exact review snapshot",
        expanded=False,
    ):
        st.code(
            markdown,
            language="markdown",
        )

    has_not_authorized = any(
        _professional_review_result_value(
            evaluation
        )
        == "NOT_AUTHORIZED"
        for evaluation
        in evaluations
    )

    if has_not_authorized:
        st.error(
            "Approval for reliance is unavailable because at least one statement "
            "goes beyond what the current case assessment presently supports. "
            "You may reject the wording."
        )

    try:
        reviewer_reference = (
            _current_professional_reviewer_reference(
                case_id=case_id
            )
        )
    except (
        MatterAccessError,
        MatterMutationError,
        _DraftingUIError,
        PermissionError,
    ) as exc:
        st.error(
            "Professional review is unavailable: "
            + str(exc)
        )
        return

    st.caption(
        "Professional reviewer: "
        + reviewer_reference
    )

    form_key = (
        "case_operator_professional_review_form_"
        + case_id
        + "_"
        + task_id
        + "_"
        + draft_id
        + "_"
        + previewed_target_id
    )

    with st.form(
        form_key
    ):
        factual_basis_reviewed = (
            st.checkbox(
                "I have reviewed the factual basis for this wording."
            )
        )
        legal_authorities_reviewed = (
            st.checkbox(
                "I have reviewed the legal authorities relevant to this wording."
            )
        )
        unverified_authorities_remaining = (
            st.number_input(
                "Unverified legal authorities remaining",
                min_value=0,
                step=1,
                value=0,
            )
        )
        professional_judgment_completed = (
            st.checkbox(
                "I have applied my professional judgment to this wording."
            )
        )
        court_or_tribunal_reliance = (
            st.checkbox(
                "This wording is intended for reliance in court or tribunal."
            )
        )
        review_note = (
            st.text_area(
                "Professional review note",
                value="",
            )
        )

        approve_clicked = (
            st.form_submit_button(
                "Approve for reliance",
                type="primary",
                disabled=has_not_authorized,
            )
        )
        reject_clicked = (
            st.form_submit_button(
                "Reject wording"
            )
        )

    if not (
        approve_clicked
        or reject_clicked
    ):
        return

    if not _clean(
        review_note
    ):
        st.error(
            "Enter a professional review note before recording a decision."
        )
        return

    if approve_clicked:
        if not factual_basis_reviewed:
            st.error(
                "Confirm that you have reviewed the factual basis before approval."
            )
            return

        if not legal_authorities_reviewed:
            st.error(
                "Confirm that you have reviewed the legal authorities before approval."
            )
            return

        if int(
            unverified_authorities_remaining
        ) != 0:
            st.error(
                "Approval requires no unverified legal authorities to remain."
            )
            return

        if not professional_judgment_completed:
            st.error(
                "Confirm that you have applied professional judgment before approval."
            )
            return

        decision = (
            WorkProductReleaseDecision.APPROVED_FOR_RELIANCE
        )

    else:
        if court_or_tribunal_reliance:
            st.error(
                "Rejected wording cannot be marked for court or tribunal reliance."
            )
            return

        decision = (
            WorkProductReleaseDecision.REJECTED
        )

    try:
        fresh_draft = (
            _load_exact_saved_working_draft(
                case_id=case_id,
                task_id=task_id,
                draft_id=draft_id,
            )
        )

        current_authority = (
            load_active_governed_analytical_authority(
                case_id
            )
        )

        if current_authority is None:
            raise _DraftingUIError(
                "No current case assessment is available."
            )

        reviewer_reference = (
            _current_professional_reviewer_reference(
                case_id=case_id
            )
        )

        result = (
            record_working_draft_professional_release(
                draft=fresh_draft,
                authority=current_authority,
                decision=decision,
                factual_basis_reviewed=
                    factual_basis_reviewed,
                legal_authorities_reviewed=
                    legal_authorities_reviewed,
                unverified_authorities_remaining=
                    int(
                        unverified_authorities_remaining
                    ),
                professional_judgment_completed=
                    professional_judgment_completed,
                court_or_tribunal_reliance=
                    court_or_tribunal_reliance,
                reviewer_reference=
                    reviewer_reference,
                review_note=
                    _clean(
                        review_note
                    ),
                expected_target_id=
                    previewed_target_id,
            )
        )

    except (
        DraftingWorkingDraftError,
        GovernedAnalyticalAuthorityProviderError,
        MatterAccessError,
        MatterMutationError,
        WorkingDraftProfessionalReleaseError,
        _DraftingUIError,
        PermissionError,
    ):
        _clear_drafting_professional_review_state()
        st.error(
            "The professional decision could not be confirmed against the "
            "reviewed snapshot. Prepare a fresh professional review before "
            "taking any further action."
        )
        return
    except Exception:
        _clear_drafting_professional_review_state()
        st.error(
            "The professional decision could not be confirmed safely. "
            "Prepare a fresh professional review before taking any further action."
        )
        return

    state = getattr(
        getattr(
            result,
            "release_projection",
            None,
        ),
        "state",
        "",
    )

    if hasattr(
        state,
        "value",
    ):
        state = getattr(
            state,
            "value",
        )

    st.session_state[
        _DRAFTING_PROFESSIONAL_REVIEW_RESULT_KEY
    ] = {
        "case_id":
            case_id,
        "task_id":
            task_id,
        "draft_id":
            draft_id,
        "decision":
            _clean(
                getattr(
                    decision,
                    "value",
                    decision,
                )
            ),
        "state":
            _clean(
                state
            ),
    }

    _clear_drafting_professional_review_state(
        preserve_result=True
    )
    st.rerun()


def _render_saved_working_drafts(
    *,
    case_id: str,
    task_id: str,
) -> None:
    try:
        drafts = (
            load_working_drafts(
                case_id,
                task_id,
            )
        )
    except DraftingWorkingDraftError as exc:
        _clear_drafting_professional_review_state()
        st.error(
            "Saved working drafts could not be validated: "
            + str(exc)
        )
        return

    if not drafts:
        _clear_drafting_professional_review_state()
        return

    draft_by_id = {}

    for draft in drafts:
        draft_id = _clean(
            getattr(
                draft,
                "draft_id",
                "",
            )
        )

        if not draft_id:
            _clear_drafting_professional_review_state()
            st.error(
                "Saved working drafts contain an item without a stable identity."
            )
            return

        if draft_id in draft_by_id:
            _clear_drafting_professional_review_state()
            st.error(
                "Saved working drafts contain a duplicate identity."
            )
            return

        draft_by_id[
            draft_id
        ] = draft

    try:
        approved_products = (
            load_approved_working_draft_products(
                case_id
            )
        )
    except DraftingApprovedWorkProductError as exc:
        st.error(
            "Approved work products could not be validated: "
            + str(exc)
        )
        return

    approved_by_draft_id = {}

    for product in approved_products:
        approved_draft_id = _clean(
            getattr(
                product,
                "draft_id",
                "",
            )
        )

        if not approved_draft_id:
            st.error(
                "Approved work products contain an item without a stable draft identity."
            )
            return

        if approved_draft_id in approved_by_draft_id:
            st.error(
                "Approved work products contain a duplicate draft identity."
            )
            return

        approved_by_draft_id[
            approved_draft_id
        ] = product

    result_marker = (
        st.session_state.pop(
            _DRAFTING_PROFESSIONAL_REVIEW_RESULT_KEY,
            None,
        )
    )

    if isinstance(
        result_marker,
        dict,
    ):
        if (
            _clean(
                result_marker.get(
                    "case_id",
                    "",
                )
            )
            == _clean(
                case_id
            )
            and _clean(
                result_marker.get(
                    "task_id",
                    "",
                )
            )
            == _clean(
                task_id
            )
        ):
            decision_value = _clean(
                result_marker.get(
                    "decision",
                    "",
                )
            ).upper()

            if (
                decision_value
                == "APPROVED_FOR_RELIANCE"
            ):
                st.success(
                    "Professional decision recorded: approved for reliance."
                )
            elif decision_value == "REJECTED":
                st.info(
                    "Professional decision recorded: wording rejected."
                )

    with st.expander(
        "Saved working drafts "
        + f"({len(drafts)})",
        expanded=False,
    ):
        selected_draft_id = (
            st.selectbox(
                "Working draft to review",
                options=tuple(
                    draft_by_id
                ),
                index=None,
                format_func=lambda value:
                    _working_draft_review_label(
                        draft_by_id[
                            value
                        ]
                    ),
                key=(
                    "case_operator_professional_review_draft_"
                    + case_id
                    + "_"
                    + task_id
                ),
                placeholder="Select a saved working draft",
            )
        )

        for draft in reversed(
            drafts[-5:]
        ):
            st.markdown(
                "**"
                + _clean(
                    getattr(
                        draft,
                        "title",
                        "Working draft",
                    )
                )
                + "**"
            )

            recorded_at = _clean(
                getattr(
                    draft,
                    "recorded_at",
                    "",
                )
            )

            if recorded_at:
                st.caption(
                    "Saved "
                    + recorded_at
                )

            listed_draft_id = _clean(
                getattr(
                    draft,
                    "draft_id",
                    "",
                )
            )

            approved_product = (
                approved_by_draft_id.get(
                    listed_draft_id
                )
            )

            if approved_product is None:
                st.caption(
                    "Working material only - not approval for reliance."
                )
            else:
                st.success(
                    "Approved for internal professional reliance"
                )

                approved_by = _clean(
                    getattr(
                        approved_product,
                        "reviewer_reference",
                        "",
                    )
                )

                approved_at = _clean(
                    getattr(
                        approved_product,
                        "approved_at",
                        "",
                    )
                )

                if approved_by and approved_at:
                    st.caption(
                        "Approved by "
                        + approved_by
                        + " on "
                        + approved_at
                    )

                if bool(
                    getattr(
                        approved_product,
                        "court_or_tribunal_reliance",
                        False,
                    )
                ):
                    st.warning(
                        "Approved for court or tribunal reliance"
                    )
                else:
                    st.info(
                        "Not approved for court or tribunal reliance"
                    )

        if not selected_draft_id:
            return

        selected_draft = (
            draft_by_id.get(
                selected_draft_id
            )
        )

        if selected_draft is None:
            _clear_drafting_professional_review_state()
            st.error(
                "The selected saved working draft is no longer available."
            )
            return

        selected_approved_product = (
            approved_by_draft_id.get(
                selected_draft_id
            )
        )

        if selected_approved_product is not None:
            with st.expander(
                "View professional decision",
                expanded=False,
            ):
                st.success(
                    "Approved for internal professional reliance"
                )

                approved_by = _clean(
                    getattr(
                        selected_approved_product,
                        "reviewer_reference",
                        "",
                    )
                )

                approved_at = _clean(
                    getattr(
                        selected_approved_product,
                        "approved_at",
                        "",
                    )
                )

                if approved_by and approved_at:
                    st.caption(
                        "Approved by "
                        + approved_by
                        + " on "
                        + approved_at
                    )

                review_note = _clean(
                    getattr(
                        selected_approved_product,
                        "review_note",
                        "",
                    )
                )

                if not review_note:
                    st.error(
                        "The stored professional review note could not be displayed."
                    )
                else:
                    st.markdown(
                        "**Professional review note**"
                    )
                    st.write(
                        review_note
                    )

                if bool(
                    getattr(
                        selected_approved_product,
                        "court_or_tribunal_reliance",
                        False,
                    )
                ):
                    st.warning(
                        "Approved for court or tribunal reliance"
                    )
                else:
                    st.info(
                        "Not approved for court or tribunal reliance"
                    )

                st.caption(
                    "This exact saved draft already has a professional decision. "
                    "The normal solicitor workflow does not create a second decision."
                )

            _clear_drafting_professional_review_state()
            return

        _render_working_draft_professional_review(
            case_id=case_id,
            task_id=task_id,
            draft=selected_draft,
        )
def _render_drafting_workflow(
    *,
    case_id: str,
    task: object,
    history: tuple[Any, ...],
) -> None:
    task_id = _clean(
        getattr(
            task,
            "task_id",
            "",
        )
    )

    if not task_id:
        return

    stored_context = (
        st.session_state.get(
            _DRAFTING_CONTEXT_KEY
        )
    )

    if (
        stored_context is not None
        and not _drafting_context_matches(
            stored_context,
            case_id=case_id,
            task_id=task_id,
        )
    ):
        _clear_drafting_state()

    saved_marker = (
        st.session_state.pop(
            _DRAFTING_SAVED_KEY,
            None,
        )
    )

    if saved_marker:
        st.success(
            "Working draft saved. It remains working material and "
            "has not been approved for reliance."
        )

    try:
        receipts = tuple(
            load_task_work_retrieval_receipts(
                case_id,
                task_id,
            )
        )

        scopes = tuple(
            load_task_work_authority_scopes(
                case_id,
                task_id,
            )
        )

        rows = (
            _task_work_scope_capture_rows(
                history=tuple(
                    history
                ),
                receipts=receipts,
                scopes=scopes,
            )
        )
    except (
        TaskWorkRetrievalReceiptError,
        TaskWorkAuthorityScopeError,
    ) as exc:
        st.error(
            "Draft preparation is unavailable because the recorded "
            "task work could not be validated: "
            + str(exc)
        )
        return

    if not rows:
        return

    st.markdown(
        "### Prepare draft"
    )

    st.caption(
        "Create proposed wording from recorded work for this task. "
        "Nothing is saved until you choose Save as working draft."
    )

    try:
        authority = (
            load_active_governed_analytical_authority(
                case_id
            )
        )
    except GovernedAnalyticalAuthorityProviderError as exc:
        st.error(
            "Draft preparation is unavailable because the current "
            "case assessment could not be validated: "
            + str(exc)
        )
        return

    if authority is None:
        st.error(
            "Draft preparation is unavailable because there is no "
            "current case assessment."
        )
        return

    current_rows = []
    stale_scope_count = 0

    for (
        progress,
        receipt,
        existing_scope,
    ) in rows:
        if existing_scope is None:
            continue

        try:
            resolution = (
                resolve_task_work_authority_scope(
                    existing_scope,
                    authority=authority,
                )
            )
        except TaskWorkAuthorityScopeError:
            stale_scope_count += 1
            continue

        current_rows.append(
            (
                progress,
                receipt,
                existing_scope,
                resolution,
            )
        )

    if stale_scope_count:
        st.warning(
            "Some earlier work can no longer be used for drafting because "
            "its professional work scope does not match the current case assessment."
        )

    if not current_rows:
        st.info(
            "Set a current work scope for recorded task work above before "
            "preparing a draft."
        )

        _render_saved_working_drafts(
            case_id=case_id,
            task_id=task_id,
        )
        return

    row_by_progress_id = {}

    for row in current_rows:
        progress = row[0]

        progress_id = _clean(
            getattr(
                progress,
                "progress_id",
                "",
            )
        )

        if not progress_id:
            continue

        if progress_id in row_by_progress_id:
            st.error(
                "Draft preparation stopped because recorded work contains "
                "a duplicate identity."
            )
            return

        row_by_progress_id[
            progress_id
        ] = row

    prepared = (
        st.session_state.get(
            _DRAFTING_PREPARED_KEY
        )
    )

    prepared_context = (
        st.session_state.get(
            _DRAFTING_CONTEXT_KEY
        )
    )

    if prepared is not None:
        if not isinstance(
            prepared,
            PreparedWorkingDraft,
        ):
            _clear_drafting_state()
            prepared = None

        elif not isinstance(
            prepared_context,
            dict,
        ):
            _clear_drafting_state()
            prepared = None

        else:
            context_progress_id = (
                _clean(
                    prepared_context.get(
                        "progress_id",
                        ""
                    )
                )
            )

            context_scope_id = (
                _clean(
                    prepared_context.get(
                        "scope_binding_id",
                        ""
                    )
                )
            )

            context_element_id = (
                _clean(
                    prepared_context.get(
                        "element_id",
                        ""
                    )
                )
            )

            row = row_by_progress_id.get(
                context_progress_id
            )

            if row is None:
                _clear_drafting_state()
                prepared = None
                st.warning(
                    "The proposed draft is no longer current. "
                    "Generate it again from the recorded work."
                )

            else:
                scope = row[2]
                resolution = row[3]

                current_element_ids = {
                    _clean(
                        getattr(
                            element,
                            "element_id",
                            "",
                        )
                    )
                    for element
                    in resolution.elements
                }

                if (
                    _clean(
                        getattr(
                            scope,
                            "binding_id",
                            "",
                        )
                    )
                    != context_scope_id
                    or context_element_id
                    not in current_element_ids
                ):
                    _clear_drafting_state()
                    prepared = None
                    st.warning(
                        "The proposed draft is no longer current. "
                        "Generate it again from the current work scope."
                    )

    if prepared is not None:
        st.markdown(
            "#### Proposed draft"
        )

        st.write(
            "**"
            + _clean(
                getattr(
                    prepared.draft,
                    "title",
                    "Working draft",
                )
            )
            + "**"
        )

        purpose = _clean(
            getattr(
                prepared.draft,
                "purpose",
                "",
            )
        )

        if purpose:
            st.caption(
                purpose
            )

        st.caption(
            "Review each proposed statement and its check against the "
            "current case assessment before saving. Saving creates working "
            "material only; it does not approve the wording for reliance."
        )

        statements = tuple(
            getattr(
                prepared.draft,
                "statements",
                (),
            )
        )

        evaluations = tuple(
            getattr(
                prepared.authority_evaluation,
                "statement_evaluations",
                (),
            )
        )

        if len(
            statements
        ) != len(
            evaluations
        ):
            st.error(
                "The proposed draft cannot be reviewed because its checks "
                "do not cover every statement."
            )
            return

        for index, (
            statement,
            evaluation,
        ) in enumerate(
            zip(
                statements,
                evaluations,
                strict=True,
            ),
            start=1,
        ):
            with st.container(
                border=True
            ):
                st.markdown(
                    f"**Proposed wording {index}**"
                )

                st.write(
                    _clean(
                        getattr(
                            statement,
                            "text",
                            "",
                        )
                    )
                )

                check = getattr(
                    evaluation,
                    "check",
                    None,
                )

                result = getattr(
                    check,
                    "result",
                    None,
                )

                kind, message = (
                    _drafting_check_presentation(
                        result
                    )
                )

                if kind == "success":
                    st.success(
                        message
                    )
                elif kind == "warning":
                    st.warning(
                        message
                    )
                else:
                    st.error(
                        message
                    )

        save_col, discard_col = (
            st.columns(2)
        )

        save_clicked = (
            save_col.button(
                "Save as working draft",
                key=(
                    "case_operator_drafting_save_"
                    + task_id
                ),
                type="primary",
            )
        )

        discard_clicked = (
            discard_col.button(
                "Discard proposed draft",
                key=(
                    "case_operator_drafting_discard_"
                    + task_id
                ),
            )
        )

        if discard_clicked:
            _clear_drafting_state()
            st.rerun()

        if save_clicked:
            try:
                (
                    progress,
                    retrieval_receipt,
                    scope,
                    current_authority,
                    _creator_reference,
                ) = (
                    _load_drafting_action_context(
                        case_id=case_id,
                        task=task,
                        progress_id=_clean(
                            prepared_context.get(
                                "progress_id",
                                "",
                            )
                        ),
                        element_id=_clean(
                            prepared_context.get(
                                "element_id",
                                "",
                            )
                        ),
                    )
                )

                recorded = (
                    record_prepared_working_draft(
                        prepared=prepared,
                        task=task,
                        progress=progress,
                        retrieval_receipt=
                            retrieval_receipt,
                        scope=scope,
                        authority=
                            current_authority,
                    )
                )

            except (
                _DraftingUIError,
                DraftingWorkingDraftOrchestrationError,
                DraftingWorkingDraftError,
                TaskWorkProgressError,
                TaskWorkRetrievalReceiptError,
                TaskWorkAuthorityScopeError,
                GovernedAnalyticalAuthorityProviderError,
                MatterAccessError,
                MatterMutationError,
                PermissionError,
            ) as exc:
                st.error(
                    "The working draft was not saved: "
                    + str(exc)
                )
                return

            st.session_state[
                _DRAFTING_SAVED_KEY
            ] = _clean(
                getattr(
                    recorded.draft,
                    "draft_id",
                    "",
                )
            ) or "saved"

            _clear_drafting_state(
                preserve_saved=True
            )

            st.rerun()

        _render_saved_working_drafts(
            case_id=case_id,
            task_id=task_id,
        )

        return

    progress_options = tuple(
        row_by_progress_id
    )

    selected_progress_id = (
        st.selectbox(
            "Work to draft from",
            options=
                progress_options,
            index=None,
            placeholder=
                "Select recorded work",
            format_func=lambda value: (
                "Recorded work"
                + (
                    " ? "
                    + _clean(
                        getattr(
                            row_by_progress_id[
                                value
                            ][0],
                            "recorded_at",
                            "",
                        )
                    )
                    if _clean(
                        getattr(
                            row_by_progress_id[
                                value
                            ][0],
                            "recorded_at",
                            "",
                        )
                    )
                    else ""
                )
            ),
            key=(
                "case_operator_drafting_progress_"
                + task_id
            ),
        )
    )

    if selected_progress_id is None:
        _render_saved_working_drafts(
            case_id=case_id,
            task_id=task_id,
        )
        return

    selected_row = (
        row_by_progress_id[
            selected_progress_id
        ]
    )

    selected_scope = (
        selected_row[2]
    )

    selected_resolution = (
        selected_row[3]
    )

    element_by_id = {
        _clean(
            getattr(
                element,
                "element_id",
                "",
            )
        ): element
        for element
        in selected_resolution.elements
        if _clean(
            getattr(
                element,
                "element_id",
                "",
            )
        )
    }

    selected_element_id = (
        st.selectbox(
            "Draft focus",
            options=
                tuple(
                    element_by_id
                ),
            index=None,
            placeholder=
                "Select the part of the case assessment to draft",
            format_func=lambda value: (
                _task_work_scope_element_label(
                    element_by_id[
                        value
                    ]
                )
            ),
            key=(
                "case_operator_drafting_element_"
                + task_id
                + "_"
                + selected_progress_id
            ),
        )
    )

    if selected_element_id is None:
        _render_saved_working_drafts(
            case_id=case_id,
            task_id=task_id,
        )
        return

    default_title = (
        _clean(
            getattr(
                task,
                "title",
                "",
            )
        )
        or "Working draft"
    )

    default_purpose = (
        _clean(
            getattr(
                task,
                "why_it_matters",
                "",
            )
        )
        or _clean(
            getattr(
                task,
                "originating_question",
                "",
            )
        )
        or "Prepare working wording from the selected recorded work."
    )

    form_key = (
        "case_operator_drafting_generate_"
        + task_id
        + "_"
        + selected_progress_id
        + "_"
        + selected_element_id
    )

    with st.form(
        form_key,
        clear_on_submit=False,
    ):
        title = (
            st.text_input(
                "Draft title",
                value=
                    default_title,
            )
        )

        purpose = (
            st.text_area(
                "Purpose",
                value=
                    default_purpose,
            )
        )

        generate_clicked = (
            st.form_submit_button(
                "Generate draft",
                type="primary",
            )
        )

    if generate_clicked:
        if not _clean(title):
            st.error(
                "Enter a draft title before generating."
            )
            return

        if not _clean(purpose):
            st.error(
                "Enter the purpose of the draft before generating."
            )
            return

        try:
            (
                progress,
                retrieval_receipt,
                fresh_scope,
                current_authority,
                creator_reference,
            ) = (
                _load_drafting_action_context(
                    case_id=case_id,
                    task=task,
                    progress_id=
                        selected_progress_id,
                    element_id=
                        selected_element_id,
                )
            )

            with st.spinner(
                "Preparing proposed wording..."
            ):
                candidate = (
                    generate_working_draft_candidate(
                        client=
                            _legal_answer_provider_client(),
                        model=
                            INTERACTIVE_CHAT_MODEL,
                        task=task,
                        progress=progress,
                        retrieval_receipt=
                            retrieval_receipt,
                        scope=fresh_scope,
                        authority=
                            current_authority,
                        element_id=
                            selected_element_id,
                        reasoning_effort=
                            INTERACTIVE_REASONING_EFFORT,
                    )
                )

                prepared = (
                    prepare_generated_working_draft(
                        candidate=
                            candidate,
                        task=task,
                        progress=progress,
                        retrieval_receipt=
                            retrieval_receipt,
                        scope=fresh_scope,
                        authority=
                            current_authority,
                        title=
                            _clean(title),
                        purpose=
                            _clean(purpose),
                        creator_reference=
                            creator_reference,
                    )
                )

        except (
            _DraftingUIError,
            DraftingWorkingDraftGenerationError,
            DraftingWorkingDraftOrchestrationError,
            DraftingWorkingDraftError,
            TaskWorkProgressError,
            TaskWorkRetrievalReceiptError,
            TaskWorkAuthorityScopeError,
            GovernedAnalyticalAuthorityProviderError,
            MatterAccessError,
            MatterMutationError,
            PermissionError,
        ) as exc:
            st.error(
                "The draft could not be prepared. Nothing has been saved: "
                + str(exc)
            )
            return

        st.session_state[
            _DRAFTING_PREPARED_KEY
        ] = prepared

        st.session_state[
            _DRAFTING_CONTEXT_KEY
        ] = {
            "case_id":
                case_id,
            "task_id":
                task_id,
            "progress_id":
                selected_progress_id,
            "scope_binding_id":
                _clean(
                    getattr(
                        fresh_scope,
                        "binding_id",
                        "",
                    )
                ),
            "element_id":
                selected_element_id,
        }

        st.rerun()

    _render_saved_working_drafts(
        case_id=case_id,
        task_id=task_id,
    )



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

    ready_tasks, blocked_tasks, unavailable_tasks = _project_approved_task_queue(
        case_id=case_id,
        open_tasks=open_tasks,
    )

    ordered_tasks = ready_tasks + blocked_tasks + unavailable_tasks

    task_by_id = {
        _clean(getattr(task, "task_id", "")): task
        for task in ordered_tasks
        if _clean(getattr(task, "task_id", ""))
    }
    task_ids = tuple(task_by_id)

    if ready_tasks:
        recommended_task = ready_tasks[0]
        st.markdown("**Recommended next approved task**")
        st.write(_clean(getattr(recommended_task, "title", "Task")))
        st.caption(
            "Case Operator has prioritised approved work that can proceed now. "
            "Blocked task work remains preserved and can still be inspected manually."
        )
    elif blocked_tasks:
        st.warning(
            "All currently validated approved tasks are blocked. "
            "No substitute task has been selected automatically."
        )

    if blocked_tasks:
        st.caption(
            f"{len(blocked_tasks)} approved task(s) currently have a latest substantive "
            "BLOCKED outcome and have been moved behind READY work in this queue."
        )

    if unavailable_tasks:
        st.warning(
            "Some approved task histories could not be validated for automatic queue "
            "ranking. Those tasks remain available for manual inspection."
        )

    if not task_ids:
        st.error("No approved task could be projected safely for task execution.")
        _render_task_execution_result(case_id=case_id, tasks=all_tasks)
        return

    handoff_from_task_id = _clean(
        st.session_state.pop(_TASK_POST_BLOCK_HANDOFF_KEY, "")
    )

    if handoff_from_task_id:
        handoff_target = _post_block_handoff_target(
            handoff_from_task_id=handoff_from_task_id,
            current_selected_task_id=_clean(
                st.session_state.get("case_operator_approved_task", "")
            ),
            ready_tasks=ready_tasks,
        )

        if handoff_target is not None:
            st.session_state["case_operator_approved_task"] = handoff_target

            target_task = task_by_id.get(handoff_target)

            st.info(
                "The task just worked is now blocked. "
                "Case Operator has moved to the next approved task that can proceed: "
                + _clean(getattr(target_task, "title", "Task"))
            )

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

    _render_task_work_scope_capture(
        case_id=case_id,
        task=selected_task,
        history=tuple(history),
    )

    _render_drafting_workflow(
        case_id=case_id,
        task=selected_task,
        history=tuple(history),
    )

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
            persisted_answer = result.get("answer")

            if (
                isinstance(persisted_answer, str)
                and extract_task_outcome(persisted_answer) == "BLOCKED"
            ):
                st.session_state[
                    _TASK_POST_BLOCK_HANDOFF_KEY
                ] = selected_task_id

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
