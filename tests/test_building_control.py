from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.exceptions import ValidationAppError
from app.schemas.building_control import BuildingControlUpdate
from app.services.building_control import (
    FOUND,
    NOT_FOUND,
    UNKNOWN,
    _to_out,
    effective_status,
    set_manual,
    summarize,
)


def _row(
    *,
    manual_status: str | None = None,
    scan_detected: bool = False,
    scan_status: str | None = None,
) -> Any:
    return SimpleNamespace(
        manual_status=manual_status,
        scan_detected=scan_detected,
        scan_status=scan_status,
    )


class TestEffectiveStatus:
    def test_scan_found_folder_is_found(self) -> None:
        assert effective_status(_row(scan_detected=True, scan_status="found-folder")) == FOUND

    def test_scan_found_file_is_found(self) -> None:
        assert effective_status(_row(scan_detected=True, scan_status="found-file")) == FOUND

    def test_scan_not_found_is_not_found(self) -> None:
        assert effective_status(_row(scan_detected=False, scan_status="not-found")) == NOT_FOUND

    def test_scan_error_is_unknown(self) -> None:
        assert effective_status(_row(scan_detected=False, scan_status="error")) == UNKNOWN

    def test_no_calc_folder_is_unknown(self) -> None:
        assert effective_status(_row(scan_status="no-4-calculations")) == UNKNOWN

    def test_never_scanned_is_unknown(self) -> None:
        assert effective_status(_row()) == UNKNOWN

    def test_manual_found_overrides_negative_scan(self) -> None:
        # A director can override a scan that found nothing.
        row = _row(manual_status="found", scan_detected=False, scan_status="not-found")
        assert effective_status(row) == FOUND

    def test_manual_not_found_overrides_positive_scan(self) -> None:
        # …and override a false-positive scan hit.
        row = _row(manual_status="not_found", scan_detected=True, scan_status="found-folder")
        assert effective_status(row) == NOT_FOUND

    def test_cleared_manual_defers_to_scan(self) -> None:
        # manual_status=None means "defer to scan" — not unknown.
        assert effective_status(_row(manual_status=None, scan_detected=True)) == FOUND


class TestSummarize:
    def test_empty_is_all_zero(self) -> None:
        s = summarize([])
        assert (s.total, s.found, s.not_found, s.unknown, s.confirmed, s.found_pct) == (
            0, 0, 0, 0, 0, 0.0,
        )

    def test_counts_and_pct(self) -> None:
        rows = [
            _row(scan_detected=True),  # found (scan)
            _row(manual_status="found"),  # found (confirmed)
            _row(scan_status="not-found"),  # not_found
            _row(scan_status="error"),  # unknown
        ]
        s = summarize(rows)
        assert (s.total, s.found, s.not_found, s.unknown) == (4, 2, 1, 1)
        assert s.found_pct == 50.0

    def test_confirmed_counts_only_manual_overrides(self) -> None:
        rows = [
            _row(scan_detected=True),  # scan-only found -> not confirmed
            _row(manual_status="found"),  # confirmed
            _row(manual_status="not_found", scan_detected=True),  # confirmed override
        ]
        s = summarize(rows)
        assert s.confirmed == 2
        assert (s.found, s.not_found) == (2, 1)

    def test_pct_rounded_to_one_dp(self) -> None:
        rows = [_row(scan_detected=True), _row(scan_status="not-found"), _row(scan_status="error")]
        s = summarize(rows)  # 1 of 3 found
        assert s.found_pct == 33.3


class TestToOut:
    def _full_row(self, **over: Any) -> Any:
        base = dict(
            project_id=uuid.uuid4(),
            project=None,
            confirmed_by=None,
            scan_detected=False,
            scan_status="not-found",
            scan_detail=None,
            scan_path=None,
            scanned_at=None,
            manual_status=None,
            notes=None,
            updated_at=datetime.now(UTC),
        )
        base.update(over)
        return SimpleNamespace(**base)

    def test_null_project_yields_blank_names(self) -> None:
        out = _to_out(self._full_row())
        assert out.project_number == "" and out.project_name == ""
        assert out.director_name is None and out.manager_name is None
        assert out.effective_status == NOT_FOUND  # derived from scan_status

    def test_project_and_confirmer_names_surface(self) -> None:
        row = self._full_row(
            project=SimpleNamespace(
                number="1234",
                name="Tower",
                director=SimpleNamespace(display_name="Dee Rector"),
                manager=SimpleNamespace(display_name="Manny Ger"),
            ),
            manual_status="found",
            confirmed_by=SimpleNamespace(display_name="Dee Rector"),
        )
        out = _to_out(row)
        assert out.project_number == "1234" and out.project_name == "Tower"
        assert out.director_name == "Dee Rector" and out.manager_name == "Manny Ger"
        assert out.effective_status == FOUND and out.confirmed_by_name == "Dee Rector"


class TestSetManualValidation:
    async def test_rejects_unknown_manual_status(self) -> None:
        # The guard short-circuits before any DB access, so session/user are unused.
        with pytest.raises(ValidationAppError):
            await set_manual(
                None,  # type: ignore[arg-type]
                uuid.uuid4(),
                BuildingControlUpdate(manual_status="maybe"),
                None,  # type: ignore[arg-type]
            )

    async def test_unknown_is_not_a_valid_manual_status(self) -> None:
        # "unknown" is an effective-status output, never a director's verdict.
        with pytest.raises(ValidationAppError):
            await set_manual(
                None,  # type: ignore[arg-type]
                uuid.uuid4(),
                BuildingControlUpdate(manual_status=UNKNOWN),
                None,  # type: ignore[arg-type]
            )
