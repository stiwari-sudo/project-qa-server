from __future__ import annotations

from typing import Any

from app.services.hrb_sync import _latest_hrb_cell, find_hrb_question_id


def _structure(hrb_qid: str | None) -> dict[str, Any]:
    """A minimal form structure with (or without) an HRB-flagged question."""
    questions = [{"id": hrb_qid, "hrb_flag": True}] if hrb_qid else []
    return {"sections": [{"questions": questions}]}


def _cell(value: str, ts: str = "") -> dict[str, Any]:
    return {"value": value, "timestamp": ts, "responded_by_name": "Test"}


class TestFindHrbQuestionId:
    def test_finds_flagged_question(self) -> None:
        assert find_hrb_question_id(_structure("q-hrb")) == "q-hrb"

    def test_none_when_absent(self) -> None:
        assert find_hrb_question_id(_structure(None)) is None


class TestLatestHrbCell:
    def test_none_when_no_determination_recorded(self) -> None:
        items = [
            (_structure("q1"), {}),
            (_structure(None), {"other": _cell("Yes")}),
        ]
        assert _latest_hrb_cell(items) is None

    def test_returns_the_answered_cell(self) -> None:
        items = [(_structure("q1"), {"q1": _cell("Yes", "2026-01-01T00:00:00")})]
        result = _latest_hrb_cell(items)
        assert result is not None
        assert result["value"] == "Yes"

    def test_latest_timestamp_wins(self) -> None:
        # A determination made (or changed) later on another stage wins.
        items = [
            (_structure("q1"), {"q1": _cell("Yes", "2026-01-01T00:00:00")}),
            (_structure("q2"), {"q2": _cell("No", "2026-02-01T00:00:00")}),
        ]
        result = _latest_hrb_cell(items)
        assert result is not None
        assert result["value"] == "No"

    def test_blank_answers_are_skipped(self) -> None:
        items = [(_structure("q1"), {"q1": _cell("   ")})]
        assert _latest_hrb_cell(items) is None

    def test_form_without_hrb_question_is_skipped(self) -> None:
        items = [(_structure(None), {"q1": _cell("Yes")})]
        assert _latest_hrb_cell(items) is None

    def test_non_mapping_cell_is_ignored(self) -> None:
        # Defensive: a raw scalar in the responses blob shouldn't crash.
        items: list[tuple[dict[str, Any], dict[str, Any]]] = [
            (_structure("q1"), {"q1": "Yes"}),
        ]
        assert _latest_hrb_cell(items) is None
