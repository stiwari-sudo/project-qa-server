from __future__ import annotations

from pathlib import Path

from app.services.qa_folders import (
    CANONICAL_STAGES,
    PEER_REVIEW_CHILDREN,
    STAGE_SUBFOLDERS,
    scaffold_building_folders,
)


def _job(root: Path, name: str, stages: list[str] | None = None) -> Path:
    """Build a fake job folder with a 10 QA (optionally with stage folders) and a
    4 Calculations folder, mimicking the share layout."""
    job = root / name
    qa = job / "10 QA"
    qa.mkdir(parents=True)
    for s in stages or []:
        (qa / s).mkdir()
    (job / "4 Calculations").mkdir()
    return job


def test_scaffolds_full_qa_tree_and_calc_folder(tmp_path: Path) -> None:
    job = _job(
        tmp_path,
        "1062 - Wells House",
        ["10.1 Concept Design", "10.2 Detailed Design"],
    )

    summary = scaffold_building_folders(tmp_path, "1062", "Block B")

    b = job / "10 QA" / "Block B"
    # Every stage gets every evidence subfolder…
    for stage in ("10.1 Concept Design", "10.2 Detailed Design"):
        for sub in STAGE_SUBFOLDERS:
            assert (b / stage / sub).is_dir()
        for child in PEER_REVIEW_CHILDREN:
            assert (b / stage / "Peer Review" / child).is_dir()
    # …and the calc side gets just the building parent.
    assert (job / "4 Calculations" / "Block B").is_dir()
    assert summary["created"] > 0
    assert summary["error"] == 0


def test_leaves_existing_main_building_layout_untouched(tmp_path: Path) -> None:
    job = _job(tmp_path, "1062 - Wells House", ["10.1 Concept Design"])

    scaffold_building_folders(tmp_path, "1062", "Block B")

    # The flat stage folder (the primary building's QA) is not moved or nested.
    assert (job / "10 QA" / "10.1 Concept Design").is_dir()


def test_idempotent_second_run_creates_nothing(tmp_path: Path) -> None:
    _job(tmp_path, "1062 - Wells House", ["10.1 Concept Design"])

    scaffold_building_folders(tmp_path, "1062", "Block B")
    again = scaffold_building_folders(tmp_path, "1062", "Block B")

    assert again["created"] == 0
    assert again["exists"] > 0


def test_falls_back_to_canonical_stages_when_qa_empty(tmp_path: Path) -> None:
    job = _job(tmp_path, "2200 - Empty QA", stages=[])

    scaffold_building_folders(tmp_path, "2200", "Block B")

    for stage in CANONICAL_STAGES:
        assert (job / "10 QA" / "Block B" / stage / "Structural Design").is_dir()


def test_no_matching_job_folder_is_a_noop(tmp_path: Path) -> None:
    _job(tmp_path, "1062 - Wells House", ["10.1 Concept Design"])

    summary = scaffold_building_folders(tmp_path, "9999", "Block B")

    assert summary == {"created": 0, "exists": 0, "error": 0}
    assert not (tmp_path / "1062 - Wells House" / "10 QA" / "Block B").exists()


def test_number_prefix_does_not_match_longer_number(tmp_path: Path) -> None:
    # "106" must not scaffold into "1062 - …".
    _job(tmp_path, "1062 - Wells House", ["10.1 Concept Design"])

    scaffold_building_folders(tmp_path, "106", "Block B")

    assert not (tmp_path / "1062 - Wells House" / "10 QA" / "Block B").exists()


def test_sanitises_illegal_characters_in_building_name(tmp_path: Path) -> None:
    job = _job(tmp_path, "1062 - Wells House", ["10.1 Concept Design"])

    scaffold_building_folders(tmp_path, "1062", 'Blk/B?: "2"')

    # Forbidden characters (/ ? : " ) are stripped; the rest is preserved.
    assert (job / "10 QA" / "BlkB 2").is_dir()


def test_blank_building_name_is_skipped(tmp_path: Path) -> None:
    _job(tmp_path, "1062 - Wells House", ["10.1 Concept Design"])

    summary = scaffold_building_folders(tmp_path, "1062", "  ///  ")

    assert summary == {"created": 0, "exists": 0, "error": 0}
