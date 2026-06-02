from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.form import QaFormDefinition
from app.repositories import forms as forms_repo
from app.repositories import stages as stages_repo

EVIDENCE_OPTIONS = ["N/A", "No", "Yes w/o Evidence", "Yes w/ Evidence"]
YES_NO_OPTIONS = ["Yes", "No"]

# stage order -> short code used in question ids (q_<code>_<section>_<n>).
STAGE_CODES: dict[int, str] = {
    1: "concept",
    2: "detailed",
    3: "pretender",
    4: "precon",
    5: "site",
    6: "archive",
}
# Stages whose Structural-Design section carries the tracked calc-package question.
CALC_PACK_STAGES = {"detailed", "pretender", "precon"}


def _q(
    qid: str,
    text: str,
    *,
    task_number: str | None = None,
    input_type: str = "dropdown",
    options: list[str] | None = None,
    help_text: str | None = None,
    hrb_flag: bool = False,
    has_subform: bool = False,
    trigger_value: str | None = None,
    subform: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": qid,
        "text": text,
        "task_number": task_number,
        "input_type": input_type,
        "options": options or [],
        "help_text": help_text,
        "hrb_flag": hrb_flag,
        "has_subform": has_subform,
        "trigger_value": trigger_value,
        "subform": subform,
    }


def _peer_review(code: str) -> dict[str, Any]:
    return {
        "id": f"sec_{code}_pr",
        "title": "Peer Review",
        "order": 1,
        "questions": [
            _q(
                f"q_{code}_pr_1",
                "Has a peer review been scoped and recorded for this stage?",
                task_number="1.1",
                options=EVIDENCE_OPTIONS,
                help_text="Attach the peer-review scope note as evidence.",
            ),
            _q(
                f"q_{code}_pr_2",
                "Was an independent design check carried out?",
                task_number="1.2",
                options=EVIDENCE_OPTIONS,
                has_subform=True,
                trigger_value="Yes w/ Evidence",
                subform={
                    "id": f"sub_{code}_pr_2",
                    "questions": [
                        _q(
                            f"q_{code}_pr_2a",
                            "Name of the independent checker.",
                            input_type="text",
                        ),
                        _q(
                            f"q_{code}_pr_2b",
                            "Date the independent check was signed off.",
                            input_type="date",
                        ),
                    ],
                },
            ),
        ],
    }


def _structural_design(code: str) -> dict[str, Any]:
    questions = [
        _q(
            f"q_{code}_sd_1",
            "Have the design basis and load assumptions been agreed and recorded?",
            task_number="2.1",
            options=EVIDENCE_OPTIONS,
        ),
        _q(
            f"q_{code}_sd_2",
            "Have the primary structural elements been analysed?",
            task_number="2.2",
            options=EVIDENCE_OPTIONS,
        ),
        _q(
            f"q_{code}_sd_3",
            "Have stability and robustness been demonstrated?",
            task_number="2.3",
            options=EVIDENCE_OPTIONS,
        ),
        _q(
            f"q_{code}_sd_4",
            "Have foundation loads been issued to the geotechnical team?",
            task_number="2.4",
            options=EVIDENCE_OPTIONS,
        ),
    ]
    if code in CALC_PACK_STAGES:
        questions.append(
            _q(
                f"q_{code}_sd_5",
                "Is the structural calculations package complete and checked?",
                task_number="2.5",
                options=EVIDENCE_OPTIONS,
                help_text="Tracked for the director calc-package completion roll-up.",
            )
        )
    return {
        "id": f"sec_{code}_sd",
        "title": "Structural Design",
        "order": 2,
        "questions": questions,
    }


def _civil_design(code: str) -> dict[str, Any]:
    return {
        "id": f"sec_{code}_cd",
        "title": "Civil Design",
        "order": 3,
        "questions": [
            _q(
                f"q_{code}_cd_1",
                "Have drainage and levels been coordinated with the structural design?",
                task_number="3.1",
                options=EVIDENCE_OPTIONS,
            ),
            _q(
                f"q_{code}_cd_2",
                "Have external works interfaces been resolved?",
                task_number="3.2",
                options=EVIDENCE_OPTIONS,
            ),
        ],
    }


def _highways_design(code: str) -> dict[str, Any]:
    return {
        "id": f"sec_{code}_hd",
        "title": "Highways Design",
        "order": 4,
        "questions": [
            _q(
                f"q_{code}_hd_1",
                "TBD — highways QA questions to be supplied by the business.",
                task_number="4.1",
                input_type="textarea",
                help_text="Placeholder until the highways checklist is finalised.",
            )
        ],
    }


def _geotechnical_design(code: str) -> dict[str, Any]:
    return {
        "id": f"sec_{code}_gd",
        "title": "Geotechnical Design",
        "order": 5,
        "questions": [
            _q(
                f"q_{code}_gd_1",
                "TBD — geotechnical QA questions to be supplied by the business.",
                task_number="5.1",
                input_type="textarea",
                help_text="Placeholder until the geotechnical checklist is finalised.",
            )
        ],
    }


def _information_output(code: str) -> dict[str, Any]:
    return {
        "id": f"sec_{code}_io",
        "title": "Information Output",
        "order": 6,
        "questions": [
            _q(
                f"q_{code}_io_1",
                "Have the stage deliverables been checked and approved before issue?",
                task_number="6.1",
                options=EVIDENCE_OPTIONS,
            ),
            _q(
                f"q_{code}_io_2",
                "Has the drawing/model register been updated?",
                task_number="6.2",
                options=EVIDENCE_OPTIONS,
            ),
        ],
    }


def _building_safety_act(code: str) -> dict[str, Any]:
    return {
        "id": f"sec_{code}_bsa",
        "title": "Building Safety Act",
        "order": 7,
        "questions": [
            _q(
                f"q_{code}_bsa_1",
                "Is this a Higher-Risk Building (HRB) under the Building Safety Act 2022?",
                task_number="7.1",
                input_type="yes_no",
                options=YES_NO_OPTIONS,
                help_text="Drives the HRB register. 18m / 7+ storeys with residential use.",
                hrb_flag=True,
            ),
            _q(
                f"q_{code}_bsa_2",
                "Have BSA duty-holder responsibilities been recorded for this stage?",
                task_number="7.2",
                options=EVIDENCE_OPTIONS,
            ),
        ],
    }


def build_structure(code: str) -> dict[str, Any]:
    return {
        "sections": [
            _peer_review(code),
            _structural_design(code),
            _civil_design(code),
            _highways_design(code),
            _geotechnical_design(code),
            _information_output(code),
            _building_safety_act(code),
        ]
    }


async def seed(session: AsyncSession) -> None:
    stages = await stages_repo.list_ordered(session)
    for stage in stages:
        existing = await forms_repo.get_active_by_stage(session, stage.id)
        if existing is not None:
            continue
        code = STAGE_CODES.get(stage.order, f"stage{stage.order}")
        session.add(
            QaFormDefinition(
                name=f"{stage.name} QA",
                stage_id=stage.id,
                version=1,
                is_active=True,
                structure=build_structure(code),
            )
        )
    await session.flush()
