from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_log import Discipline, QaEventLog
from app.models.hrb import QaHighRiskBuilding
from app.models.project import Project
from app.models.response import QaProjectResponse
from app.models.user import User
from app.repositories import event_logs as event_logs_repo
from app.repositories import forms as forms_repo
from app.repositories import hrb as hrb_repo
from app.repositories import projects as projects_repo
from app.repositories import responses as responses_repo
from app.repositories import stages as stages_repo
from app.repositories import users as users_repo
from app.services import buildings as buildings_service
from app.services.scoring import calculate_completion

DEV_ENGINEER = "engineer@hts.uk.com"

USERS: list[dict[str, Any]] = [
    {"email": DEV_ENGINEER, "display_name": "Evan Engineer", "roles": ["engineer"]},
    {"email": "sam.engineer@hts.uk.com", "display_name": "Sam Engineer", "roles": ["engineer"]},
    {"email": "morgan.manager@hts.uk.com", "display_name": "Morgan Manager", "roles": ["manager"]},
    {"email": "mia.manager@hts.uk.com", "display_name": "Mia Manager", "roles": ["manager"]},
    {"email": "dana.director@hts.uk.com", "display_name": "Dana Director", "roles": ["director"]},
    {"email": "david.director@hts.uk.com", "display_name": "David Director", "roles": ["director"]},
]

# construction -> has Site-stage activity (counts in the director Overview).
# calc_complete -> answered the tracked calc-package question "Yes".
PROJECTS: list[dict[str, Any]] = [
    {"number": "24001", "name": "Riverside Tower", "sector": "Residential",
     "director": "dana.director@hts.uk.com", "manager": "morgan.manager@hts.uk.com",
     "construction": True, "calc_complete": True, "hrb": True, "deadline_in": 12},
    {"number": "24002", "name": "Harbour Bridge Strengthening", "sector": "Infrastructure",
     "director": "dana.director@hts.uk.com", "manager": "morgan.manager@hts.uk.com",
     "construction": True, "calc_complete": False, "hrb": False, "deadline_in": 5},
    {"number": "24003", "name": "City Central Library", "sector": "Civic",
     "director": "dana.director@hts.uk.com", "manager": "mia.manager@hts.uk.com",
     "construction": True, "calc_complete": True, "hrb": False, "deadline_in": 20},
    {"number": "24004", "name": "Market Hall Redevelopment", "sector": "Commercial",
     "director": "david.director@hts.uk.com", "manager": "mia.manager@hts.uk.com",
     "construction": True, "calc_complete": False, "hrb": True, "deadline_in": 2},
    {"number": "24005", "name": "Green Lane Campus", "sector": "Education",
     "director": "david.director@hts.uk.com", "manager": "morgan.manager@hts.uk.com",
     "construction": True, "calc_complete": True, "hrb": False, "deadline_in": 30},
    {"number": "24006", "name": "Old Mill Conversion", "sector": "Residential",
     "director": "david.director@hts.uk.com", "manager": "mia.manager@hts.uk.com",
     "construction": False, "calc_complete": False, "hrb": False, "deadline_in": None},
    {"number": "24007", "name": "Sky Plaza Offices", "sector": "Commercial",
     "director": "dana.director@hts.uk.com", "manager": "morgan.manager@hts.uk.com",
     "construction": False, "calc_complete": False, "hrb": False, "deadline_in": None},
    {"number": "24008", "name": "Civic Centre Annexe", "sector": "Civic",
     "director": None, "manager": "mia.manager@hts.uk.com",
     "construction": True, "calc_complete": False, "hrb": False, "deadline_in": 8},
]


async def seed_users(session: AsyncSession) -> None:
    for spec in USERS:
        if await users_repo.get_by_email(session, spec["email"]) is None:
            session.add(
                User(
                    email=spec["email"],
                    display_name=spec["display_name"],
                    roles=spec["roles"],
                )
            )
    await session.flush()


def _stamp(raw: dict[str, str], user: User) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        qid: {
            "value": value,
            "responded_by_id": str(user.id),
            "responded_by_name": user.display_name,
            "timestamp": now,
        }
        for qid, value in raw.items()
    }


def _detailed_answers(calc_complete: bool) -> dict[str, str]:
    answers = {
        "q_detailed_pr_1": "Yes w/ Evidence",
        "q_detailed_sd_1": "Yes w/ Evidence",
        "q_detailed_sd_2": "Yes w/o Evidence",
        "q_detailed_sd_3": "Yes w/ Evidence",
        "q_detailed_io_1": "Yes w/ Evidence",
    }
    answers["q_detailed_sd_5"] = "Yes w/ Evidence" if calc_complete else "No"
    return answers


def _site_answers(is_hrb: bool) -> dict[str, str]:
    return {
        "q_site_pr_1": "Yes w/ Evidence",
        "q_site_sd_1": "Yes w/ Evidence",
        "q_site_sd_2": "Yes w/o Evidence",
        "q_site_io_1": "Yes w/o Evidence",
        "q_site_bsa_1": "Yes" if is_hrb else "No",
    }


async def _make_response(
    session: AsyncSession,
    *,
    project: Project,
    stage: Any,
    raw_answers: dict[str, str],
    user: User,
    deadline: date | None = None,
) -> None:
    form = await forms_repo.get_active_by_stage(session, stage.id)
    if form is None:
        return
    building = await buildings_service.get_primary_building(session, project.id)
    if await responses_repo.get_for_building_stage(session, building.id, stage.id):
        return
    responses = _stamp(raw_answers, user)
    result = calculate_completion(form.structure, responses)
    session.add(
        QaProjectResponse(
            project_id=project.id,
            building_id=building.id,
            form_id=form.id,
            stage_id=stage.id,
            responses=responses,
            completion_percentage=result.completion_percentage,
            total_questions=result.total_questions,
            answered_questions=result.answered_questions,
            deadline=deadline,
            last_updated_by_id=user.id,
        )
    )
    await session.flush()


async def seed_projects(session: AsyncSession) -> None:
    users = {u.email: u for u in await users_repo.list_all(session)}
    existing = {p.number: p for p in await projects_repo.list_active(session)}
    stages = {s.order: s for s in await stages_repo.list_ordered(session)}
    engineer = users.get(DEV_ENGINEER)
    if engineer is None or 2 not in stages or 5 not in stages:
        return

    for spec in PROJECTS:
        project = existing.get(spec["number"])
        if project is None:
            director = users.get(spec["director"]) if spec["director"] else None
            manager = users.get(spec["manager"]) if spec["manager"] else None
            project = Project(
                number=spec["number"],
                name=spec["name"],
                sector=spec["sector"],
                director_id=director.id if director else None,
                manager_id=manager.id if manager else None,
            )
            session.add(project)
            await session.flush()

        await _make_response(
            session,
            project=project,
            stage=stages[2],
            raw_answers=_detailed_answers(spec["calc_complete"]),
            user=engineer,
        )

        if spec["construction"]:
            deadline = (
                date.today() + timedelta(days=spec["deadline_in"])
                if spec.get("deadline_in") is not None
                else None
            )
            await _make_response(
                session,
                project=project,
                stage=stages[5],
                raw_answers=_site_answers(spec["hrb"]),
                user=engineer,
                deadline=deadline,
            )


# Sample event logs: (project_number, stage_order|None, discipline, category, description,
# cause_reason, action_effect). Stage order maps to a seeded stage; None = unassigned.
EVENT_LOGS: list[dict[str, Any]] = [
    {"project": "24001", "stage": 5, "discipline": Discipline.STRUCTURES,
     "category": "Programme delay",
     "description": "Transfer beam rebar congestion flagged on site during pour prep.",
     "cause": "Late coordination of MEP penetrations against the structural model.",
     "action": "Reissued rebar bending schedule; 2-day hold on pour to resolve clashes."},
    {"project": "24001", "stage": 4, "discipline": Discipline.OTHER,
     "category": "Quality observation",
     "description": "Concrete cube results 3 days late from the testing house.",
     "cause": "Lab backlog over the bank-holiday weekend.",
     "action": "Chased lab; interim results confirmed strength, no programme impact."},
    {"project": "24002", "stage": 5, "discipline": Discipline.CIVILS,
     "category": "Design change",
     "description": "Bridge bearing plinth levels revised after as-built survey.",
     "cause": "Existing abutment found 40mm lower than record drawings.",
     "action": "Plinth shim detail issued; checked against bearing schedule."},
    {"project": "24003", "stage": 2, "discipline": Discipline.STRUCTURES,
     "category": "Cost impact",
     "description": "Foundation type changed from pads to a raft for the library wing.",
     "cause": "Variable made-ground depth revealed in the GI report.",
     "action": "Raft option costed with QS; client approved the uplift."},
    {"project": "24004", "stage": 5, "discipline": Discipline.GEOTECHNICAL,
     "category": "Safety / BSA",
     "description": "Temporary works to the retained facade re-checked after a wind event.",
     "cause": "Gust loads exceeded the design return period for the props.",
     "action": "Independent TW check commissioned; props augmented before access resumed."},
    {"project": "24005", "stage": 3, "discipline": Discipline.HIGHWAYS,
     "category": "Programme delay",
     "description": "Campus access road levels held pending council adoption comments.",
     "cause": "Awaiting s38 technical approval from the highways authority.",
     "action": "Pre-app meeting booked; interim haul route agreed with the contractor."},
    {"project": "24008", "stage": None, "discipline": Discipline.OTHER,
     "category": "Information request",
     "description": "Annexe brief still missing fire-strategy input from the client team.",
     "cause": "Fire consultant not yet appointed by the client.",
     "action": "Risk logged; placeholder assumptions recorded for the structural scheme."},
]


async def seed_event_logs(session: AsyncSession) -> None:
    if await event_logs_repo.list_filtered(session):
        return
    users = {u.email: u for u in await users_repo.list_all(session)}
    projects = {p.number: p for p in await projects_repo.list_active(session)}
    stages = {s.order: s for s in await stages_repo.list_ordered(session)}
    logger = users.get(DEV_ENGINEER)
    if logger is None:
        return

    for spec in EVENT_LOGS:
        project = projects.get(spec["project"])
        if project is None:
            continue
        stage = stages.get(spec["stage"]) if spec["stage"] is not None else None
        session.add(
            QaEventLog(
                project_id=project.id,
                description=spec["description"],
                cause_reason=spec["cause"],
                action_effect=spec["action"],
                category_of_impact=spec["category"],
                stage_id=stage.id if stage else None,
                discipline=spec["discipline"],
                logged_by_id=logger.id,
            )
        )
    await session.flush()


async def seed_hrb(session: AsyncSession) -> None:
    users = {u.email: u for u in await users_repo.list_all(session)}
    projects = {p.number: p for p in await projects_repo.list_active(session)}
    stages = {s.order: s for s in await stages_repo.list_ordered(session)}
    site = stages.get(5)
    checker = users.get("dana.director@hts.uk.com") or users.get(DEV_ENGINEER)
    if site is None or checker is None:
        return

    for spec in PROJECTS:
        if not spec.get("hrb"):
            continue
        project = projects.get(spec["number"])
        if project is None:
            continue
        building = await buildings_service.get_primary_building(session, project.id)
        if await hrb_repo.get_by_building_stage(session, building.id, site.id):
            continue
        session.add(
            QaHighRiskBuilding(
                project_id=project.id,
                building_id=building.id,
                stage_id=site.id,
                is_high_risk=True,
                checked_by_id=checker.id,
                notes="Flagged as Higher-Risk Building during Site-stage BSA review.",
            )
        )
    await session.flush()
