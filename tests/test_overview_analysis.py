from __future__ import annotations

from app.services.overview import (
    NO_QA_STARTED,
    NOT_SYNCED,
    _cmap_stage_counts_to_list,
    _has_yes_answer,
    _qa_stage_counts_to_list,
)


def _cell(value: str) -> dict[str, object]:
    return {"value": value, "responded_by_name": "Test"}


class TestHasYesAnswer:
    def test_yes_with_evidence_counts(self) -> None:
        assert _has_yes_answer({"q1": _cell("Yes w/ Evidence")}) is True

    def test_yes_without_evidence_counts(self) -> None:
        assert _has_yes_answer({"q1": _cell("Yes w/o Evidence")}) is True

    def test_plain_yes_counts(self) -> None:
        assert _has_yes_answer({"q1": _cell("Yes")}) is True

    def test_no_does_not_count(self) -> None:
        assert _has_yes_answer({"q1": _cell("No")}) is False

    def test_na_and_blank_do_not_count(self) -> None:
        assert _has_yes_answer({"q1": _cell("N/A"), "q2": _cell("")}) is False

    def test_legacy_placeholder_dashes_do_not_count(self) -> None:
        assert _has_yes_answer({"q1": _cell("----------")}) is False

    def test_scalar_value_supported(self) -> None:
        # Older/raw rows may store a bare scalar rather than a {value: ...} cell.
        assert _has_yes_answer({"q1": "Yes"}) is True

    def test_empty_dict_is_false(self) -> None:
        assert _has_yes_answer({}) is False

    def test_any_yes_among_many_counts(self) -> None:
        responses = {"q1": _cell("No"), "q2": _cell("N/A"), "q3": _cell("Yes w/ Evidence")}
        assert _has_yes_answer(responses) is True


class TestQaStageCountsToList:
    def test_sorted_by_lifecycle_order_with_no_qa_started_last(self) -> None:
        order = {"Concept": 1, "Detailed Design": 2, "Pre-tender": 3}
        counts = {
            "Pre-tender": 2,
            NO_QA_STARTED: 5,
            "Concept": 4,
            "Detailed Design": 1,
        }
        result = _qa_stage_counts_to_list(counts, order)
        assert [r.stage_name for r in result] == [
            "Concept",
            "Detailed Design",
            "Pre-tender",
            NO_QA_STARTED,
        ]
        assert [r.project_count for r in result] == [4, 1, 2, 5]


class TestCmapStageCountsToList:
    def test_sorted_by_count_desc_with_not_synced_last(self) -> None:
        counts = {"5 - Construction": 3, NOT_SYNCED: 100, "4 - Technical Design": 7}
        result = _cmap_stage_counts_to_list(counts)
        assert [r.stage_name for r in result] == [
            "4 - Technical Design",
            "5 - Construction",
            NOT_SYNCED,
        ]

    def test_singletons_collapse_into_other_before_not_synced(self) -> None:
        # The dirty legacy free-text values are one-offs — they must fold into a
        # single "Other" bucket, with "Not synced" still pinned last.
        counts = {
            "5 - Construction": 108,
            "4 - Technical Design": 57,
            "12 Burleigh St Roof": 1,
            "2025 additional design": 1,
            "3 - Strip out": 1,
            NOT_SYNCED: 191,
        }
        result = _cmap_stage_counts_to_list(counts)
        assert [(r.stage_name, r.project_count) for r in result] == [
            ("5 - Construction", 108),
            ("4 - Technical Design", 57),
            ("Other", 3),
            (NOT_SYNCED, 191),
        ]

    def test_no_other_bucket_when_no_long_tail(self) -> None:
        counts = {"5 - Construction": 4, "4 - Technical Design": 2}
        result = _cmap_stage_counts_to_list(counts)
        assert [r.stage_name for r in result] == [
            "5 - Construction",
            "4 - Technical Design",
        ]
