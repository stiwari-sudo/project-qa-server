"""Evidence-weighted completion scoring.

Faithful re-implementation of the legacy ``QaProjectResponse.calculate_completion``
(Django ``models.py:196-277``). Pure and DB-free so it is trivially unit-testable.

Rules:
  * For questions whose options contain "evidence":
        "Yes w/ Evidence"  -> 1.0
        "Yes w/o Evidence" -> 0.5
        "No"               -> 0.0  (still counts as answered)
        plain "Yes"/other  -> 1.0
  * For any other input type, a non-empty value -> 1.0.
  * "N/A" is excluded from BOTH the numerator and the denominator.
  * Empty/unanswered questions remain in the denominator (drag the score down).
  * Subform questions are only counted when their parent's answer equals the
    parent's ``trigger_value`` (i.e. the subform is actually shown).

  completion_percentage = total_points / (total_questions - na_count) * 100
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_NA_TOKENS = {"N/A", "NA", "N / A"}


@dataclass(frozen=True)
class CompletionResult:
    completion_percentage: float
    total_questions: int
    answered_questions: int


def _has_evidence_options(options: list[Any]) -> bool:
    if not options:
        return False
    joined = " ".join(str(opt).lower() for opt in options)
    return any(
        token in joined
        for token in ("w/ evidence", "with evidence", "w/o evidence", "without evidence")
    )


def _response_value(responses: Mapping[str, Any], question_id: str) -> str:
    raw = responses.get(question_id)
    if isinstance(raw, Mapping):
        value = raw.get("value", "")
    else:
        value = raw
    if value is None:
        return ""
    return str(value).strip()


def _collect_active_questions(
    structure: Mapping[str, Any], responses: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Flatten sections -> questions, including subform questions only when active."""
    collected: list[dict[str, Any]] = []
    for section in structure.get("sections", []) or []:
        for question in section.get("questions", []) or []:
            _collect_question(question, responses, collected)
    return collected


def _collect_question(
    question: Mapping[str, Any],
    responses: Mapping[str, Any],
    collected: list[dict[str, Any]],
) -> None:
    collected.append(dict(question))
    subform = question.get("subform")
    if not question.get("has_subform") or not subform:
        return
    trigger = question.get("trigger_value")
    answer = _response_value(responses, str(question.get("id", "")))
    if trigger is None or answer.lower() != str(trigger).strip().lower():
        return
    for sub_q in subform.get("questions", []) or []:
        _collect_question(sub_q, responses, collected)


def calculate_completion(
    structure: Mapping[str, Any], responses: Mapping[str, Any]
) -> CompletionResult:
    questions = _collect_active_questions(structure, responses)

    total_points = 0.0
    answered = 0
    na_count = 0

    for question in questions:
        qid = str(question.get("id", ""))
        value = _response_value(responses, qid)

        if value.upper() in _NA_TOKENS:
            na_count += 1
            continue
        if not value:
            # unanswered — stays in the denominator, scores nothing
            continue

        value_lower = value.lower()
        if _has_evidence_options(question.get("options", []) or []):
            if "w/ evidence" in value_lower or "with evidence" in value_lower:
                total_points += 1.0
            elif "w/o evidence" in value_lower or "without evidence" in value_lower:
                total_points += 0.5
            elif value_lower == "no":
                total_points += 0.0
            else:  # plain "Yes" / other
                total_points += 1.0
        else:
            total_points += 1.0
        answered += 1

    total_questions = len(questions) - na_count
    pct = (total_points / total_questions * 100) if total_questions > 0 else 0.0
    return CompletionResult(
        completion_percentage=round(pct, 2),
        total_questions=total_questions,
        answered_questions=answered,
    )
