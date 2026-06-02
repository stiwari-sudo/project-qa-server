from __future__ import annotations

from typing import Any

from app.services.scoring import calculate_completion

EVIDENCE_OPTIONS = ["N/A", "No", "Yes w/o Evidence", "Yes w/ Evidence"]


def _evidence_q(qid: str) -> dict[str, Any]:
    return {"id": qid, "text": qid, "input_type": "dropdown", "options": EVIDENCE_OPTIONS}


def _answer(value: str) -> dict[str, Any]:
    return {"value": value, "responded_by_id": None, "responded_by_name": "Test"}


def _structure(*questions: dict[str, Any]) -> dict[str, Any]:
    return {"sections": [{"id": "s1", "title": "S", "order": 1, "questions": list(questions)}]}


def test_worked_example_62_5_percent() -> None:
    structure = _structure(
        _evidence_q("q1"),
        _evidence_q("q2"),
        _evidence_q("q3"),
        _evidence_q("q4"),
        _evidence_q("q5"),
    )
    responses = {
        "q1": _answer("Yes w/ Evidence"),  # 1.0
        "q2": _answer("Yes w/ Evidence"),  # 1.0
        "q3": _answer("Yes w/o Evidence"),  # 0.5
        "q4": _answer("N/A"),  # excluded
        # q5 unanswered -> in denominator
    }
    result = calculate_completion(structure, responses)
    assert result.completion_percentage == 62.5
    assert result.total_questions == 4
    assert result.answered_questions == 3


def test_na_excluded_from_denominator() -> None:
    structure = _structure(_evidence_q("q1"), _evidence_q("q2"))
    responses = {"q1": _answer("Yes w/ Evidence"), "q2": _answer("N/A")}
    result = calculate_completion(structure, responses)
    assert result.completion_percentage == 100.0
    assert result.total_questions == 1
    assert result.answered_questions == 1


def test_no_scores_zero_but_counts_answered() -> None:
    structure = _structure(_evidence_q("q1"), _evidence_q("q2"))
    responses = {"q1": _answer("Yes w/ Evidence"), "q2": _answer("No")}
    result = calculate_completion(structure, responses)
    assert result.completion_percentage == 50.0
    assert result.total_questions == 2
    assert result.answered_questions == 2


def test_plain_yes_full_credit() -> None:
    q = {"id": "q1", "text": "HRB?", "input_type": "dropdown", "options": ["N/A", "Yes", "No"]}
    structure = _structure(q)
    result = calculate_completion(structure, {"q1": _answer("Yes")})
    # Non-evidence options -> any non-empty value is full credit.
    assert result.completion_percentage == 100.0


def test_non_evidence_any_value_full_credit() -> None:
    structure = _structure(
        {"id": "q1", "text": "Name", "input_type": "text"},
        {"id": "q2", "text": "Date", "input_type": "date"},
    )
    responses = {"q1": _answer("Jane Doe"), "q2": _answer("2026-01-01")}
    result = calculate_completion(structure, responses)
    assert result.completion_percentage == 100.0
    assert result.answered_questions == 2


def test_empty_drags_score_down() -> None:
    structure = _structure(_evidence_q("q1"), _evidence_q("q2"))
    responses = {"q1": _answer("Yes w/ Evidence")}  # q2 missing
    result = calculate_completion(structure, responses)
    assert result.completion_percentage == 50.0
    assert result.total_questions == 2
    assert result.answered_questions == 1


def test_subform_counted_only_when_trigger_active() -> None:
    parent = {
        "id": "p1",
        "text": "Peer review?",
        "input_type": "dropdown",
        "options": EVIDENCE_OPTIONS,
        "has_subform": True,
        "trigger_value": "Yes w/ Evidence",
        "subform": {
            "id": "sf1",
            "questions": [{"id": "p1_s1", "text": "Reviewer", "input_type": "text"}],
        },
    }
    structure = _structure(parent)

    # Trigger NOT met -> subform question excluded; only the parent counts.
    inactive = calculate_completion(structure, {"p1": _answer("No")})
    assert inactive.total_questions == 1

    # Trigger met but subform question unanswered -> 2 in denominator, 1 answered.
    active = calculate_completion(structure, {"p1": _answer("Yes w/ Evidence")})
    assert active.total_questions == 2
    assert active.answered_questions == 1
    assert active.completion_percentage == 50.0


def test_empty_form_is_zero() -> None:
    result = calculate_completion({"sections": []}, {})
    assert result.completion_percentage == 0.0
    assert result.total_questions == 0
    assert result.answered_questions == 0
