from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from app.services.building_control import (
    FORM_ONLY,
    MATCH,
    NO_SCAN,
    SCAN_ONLY,
    _agreement,
    _build_out,
    _structure_has_question,
    summarize_jobs,
)
from app.services.construction import (
    CALC_BLANK,
    CALC_NO,
    CALC_YES,
    calc_pack_complete,
    calc_pack_status,
)

CALC_IDS = ["q_detailed_sd_5", "q_pretender_sd_5", "q_precon_sd_5"]


def _cell(value: str) -> dict[str, str]:
    return {"value": value, "responded_by_name": "Test"}


def _scan(detected: bool, status: str | None = None) -> Any:
    return SimpleNamespace(
        scan_detected=detected,
        scan_status=status or ("found-folder" if detected else "not-found"),
        scan_path="J:/x" if detected else None,
        scanned_at=datetime.now(UTC),
    )


class TestCalcPackStatus:
    def test_yes_variant_is_yes(self) -> None:
        assert calc_pack_status({"q_precon_sd_5": _cell("Yes w/ Evidence")}, CALC_IDS) == CALC_YES

    def test_plain_yes_is_yes(self) -> None:
        assert calc_pack_status({"q_precon_sd_5": "Yes"}, CALC_IDS) == CALC_YES

    def test_explicit_no_is_no(self) -> None:
        assert calc_pack_status({"q_precon_sd_5": _cell("No")}, CALC_IDS) == CALC_NO

    def test_empty_is_blank(self) -> None:
        assert calc_pack_status({}, CALC_IDS) == CALC_BLANK
        assert calc_pack_status({"q_precon_sd_5": _cell("")}, CALC_IDS) == CALC_BLANK

    def test_any_yes_wins_over_no(self) -> None:
        merged = {"q_detailed_sd_5": _cell("No"), "q_precon_sd_5": _cell("Yes")}
        assert calc_pack_status(merged, CALC_IDS) == CALC_YES

    def test_complete_helper_tracks_yes(self) -> None:
        assert calc_pack_complete({"q_precon_sd_5": "Yes"}, CALC_IDS) is True
        assert calc_pack_complete({"q_precon_sd_5": _cell("No")}, CALC_IDS) is False


class TestAgreement:
    def test_no_scan_row(self) -> None:
        assert _agreement(CALC_YES, None) == NO_SCAN

    def test_both_present_is_match(self) -> None:
        assert _agreement(CALC_YES, _scan(True)) == MATCH

    def test_both_absent_is_match(self) -> None:
        # form not "yes" and scan didn't detect -> they agree it's absent
        assert _agreement(CALC_NO, _scan(False)) == MATCH
        assert _agreement(CALC_BLANK, _scan(False)) == MATCH

    def test_form_yes_scan_missing_is_form_only(self) -> None:
        assert _agreement(CALC_YES, _scan(False)) == FORM_ONLY

    def test_scan_found_form_not_yes_is_scan_only(self) -> None:
        assert _agreement(CALC_NO, _scan(True)) == SCAN_ONLY
        assert _agreement(CALC_BLANK, _scan(True)) == SCAN_ONLY


class TestSummarizeJobs:
    def test_counts_verdict_and_scan_agreement(self) -> None:
        p1, p2, p3, p4 = (uuid.uuid4() for _ in range(4))
        merged = {
            p1: {"q_precon_sd_5": _cell("Yes")},  # present, scan agrees
            p2: {"q_precon_sd_5": _cell("No")},  # absent, scan disagrees (found)
            p3: {"q_precon_sd_5": _cell("Yes")},  # present, no scan row
            # p4 has no responses -> blank, scan didn't find -> match
        }
        scans = {p1: _scan(True), p2: _scan(True), p4: _scan(False)}
        s = summarize_jobs([p1, p2, p3, p4], merged, CALC_IDS, scans)
        assert (s.total, s.present, s.absent, s.blank) == (4, 2, 1, 1)
        assert (s.scanned, s.detected, s.mismatch) == (3, 2, 1)  # only p2 mismatches


class TestStructureHasQuestion:
    def _structure(self) -> dict[str, Any]:
        return {
            "sections": [
                {"questions": [{"id": "q_a"}, {
                    "id": "q_b",
                    "subform": {"questions": [{"id": "q_b_sub"}]},
                }]},
            ]
        }

    def test_finds_top_level(self) -> None:
        assert _structure_has_question(self._structure(), "q_a") is True

    def test_finds_subform_question(self) -> None:
        assert _structure_has_question(self._structure(), "q_b_sub") is True

    def test_absent_returns_false(self) -> None:
        assert _structure_has_question(self._structure(), "q_missing") is False


class TestBuildOut:
    def _project(self) -> Any:
        return SimpleNamespace(
            id=uuid.uuid4(),
            number="2169",
            name="Avon House",
            director=SimpleNamespace(display_name="Dee Rector"),
            manager=SimpleNamespace(display_name="Manny Ger"),
        )

    def test_present_with_matching_scan(self) -> None:
        out = _build_out(self._project(), CALC_YES, _scan(True))
        assert out.present is True and out.form_status == CALC_YES
        assert out.scanned is True and out.scan_detected is True
        assert out.agreement == MATCH
        assert out.director_name == "Dee Rector" and out.project_number == "2169"

    def test_blank_without_scan(self) -> None:
        out = _build_out(self._project(), CALC_BLANK, None)
        assert out.present is False and out.scanned is False
        assert out.scan_detected is False and out.agreement == NO_SCAN
