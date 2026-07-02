from __future__ import annotations

from scripts.backfill_answer_casing import _canon_question, _canonical
from scripts.migrate_legacy import _VALUE_MAP, _clean_value, _norm_question
from seeds.forms import EVIDENCE_OPTIONS


def test_value_map_outputs_are_exactly_the_seeded_options() -> None:
    # The web matches stored values against these option strings. Scoring is
    # case-insensitive so a casing drift is invisible to scores — but it makes
    # the answer render as unselected. Lock the two constants together.
    for mapped in _VALUE_MAP.values():
        assert mapped in EVIDENCE_OPTIONS


def test_clean_value_canonicalises_evidence_case_drift() -> None:
    assert _clean_value("yes-(with evidence)") == "Yes w/ Evidence"
    assert _clean_value("Yes-(Without Evidence)") == "Yes w/o Evidence"
    assert _clean_value("Yes w/ evidence") == "Yes w/ Evidence"
    assert _clean_value("yes w/o EVIDENCE") == "Yes w/o Evidence"


def test_clean_value_keeps_blanks_and_regular_values() -> None:
    assert _clean_value("----------") == ""
    assert _clean_value(None) == ""
    assert _clean_value(" No ") == "No"


def test_backfill_targets_only_evidence_values() -> None:
    assert _canonical("Yes w/ evidence") == "Yes w/ Evidence"
    assert _canonical(" yes w/o evidence ") == "Yes w/o Evidence"
    # Already canonical → no rewrite reported.
    assert _canonical("Yes w/ Evidence") is None
    assert _canonical("No") is None
    assert _canonical(None) is None


def test_norm_question_canonicalises_legacy_option_casing() -> None:
    # The migrated form definitions carry lowercase evidence option strings —
    # a migration re-run must emit the canonical casing.
    q = _norm_question(
        {
            "id": "q1",
            "text": "t",
            "input_type": "dropdown",
            "options": ["N/A", "No", "Yes w/o evidence", "Yes w/ evidence"],
            "trigger_value": "Yes w/ evidence",
        }
    )
    assert q["options"] == list(EVIDENCE_OPTIONS)
    assert q["trigger_value"] == "Yes w/ Evidence"


def test_backfill_canonicalises_form_questions_recursively() -> None:
    q = {
        "options": ["Yes w/ evidence", "No"],
        "trigger_value": "yes w/ evidence",
        "subform": {"questions": [{"options": ["Yes w/o evidence"]}]},
    }
    assert _canon_question(q) == 3
    assert q["options"] == ["Yes w/ Evidence", "No"]
    assert q["trigger_value"] == "Yes w/ Evidence"
    assert q["subform"]["questions"][0]["options"] == ["Yes w/o Evidence"]
