"""One-off migration: legacy QA v2 (MySQL) -> standalone Project QA (Postgres).

Reads the legacy `project_qa_v2_*` tables plus the referenced `projects_project`
and `auth_user` rows, transforms the form structure to our canonical shape,
recomputes completion with our scoring service, and writes everything into the
standalone schema. Idempotent: wipes the target QA data (keeps stages) and
reloads on each run.

Run (from projectqa-api/, with the persistent cluster up):

    DATABASE_URL=postgresql+asyncpg://qa@127.0.0.1:5544/projectqa \
        ./.venv/Scripts/python.exe -m scripts.migrate_legacy
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import pymysql
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models.building import Building
from app.models.event_log import Discipline, QaEventLog
from app.models.form import QaFormDefinition
from app.models.hrb import QaHighRiskBuilding
from app.models.project import Project
from app.models.response import QaProjectResponse
from app.models.stage import Stage
from app.models.user import User
from app.services.scoring import calculate_completion
from seeds import stages as stages_seed

ACCESS_CODES = (
    r"C:\Users\stiwari\OneDrive - Heyne Tillett Steel\Documents\hts-projects"
    r"\TechandData\TechandData-Backend\access_codes.json"
)

_DISCIPLINES = {d.value: d for d in Discipline}


# --------------------------------------------------------------------------- #
# Legacy (MySQL) read
# --------------------------------------------------------------------------- #
def _mysql() -> pymysql.connections.Connection:
    with open(ACCESS_CODES) as fh:
        ac = json.load(fh)
    return pymysql.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        password=ac["LOCAL_DATABASE_PASSWORD"],
        database=ac["AZURE_DATABASE_NAME"],
        cursorclass=pymysql.cursors.DictCursor,
    )


def _as_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return default
    return value


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


# --------------------------------------------------------------------------- #
# Form-structure normalisation -> canonical shape
# --------------------------------------------------------------------------- #
_HRB_HINTS = ("high risk building", "high-risk building", "higher-risk building")


def _norm_question(q: dict[str, Any]) -> dict[str, Any]:
    text = str(q.get("text") or "")
    sub = q.get("subform")
    has_sub = bool(q.get("has_subform")) and isinstance(sub, dict)
    norm_sub: dict[str, Any] | None = None
    if has_sub and isinstance(sub, dict):
        norm_sub = {
            "id": str(sub.get("id") or "subform"),
            "questions": [_norm_question(sq) for sq in sub.get("questions", [])],
        }
    return {
        "id": str(q.get("id") or ""),
        "text": text,
        "task_number": q.get("task_number"),
        "input_type": str(q.get("input_type") or "text"),
        # Options + trigger get the same canonical casing as answer values —
        # legacy forms carry lowercase "Yes w/ evidence" option strings.
        "options": [_canon_option(o) for o in (q.get("options") or [])],
        "help_text": q.get("help_text"),
        "hrb_flag": bool(q.get("hrb_flag"))
        or any(h in text.lower() for h in _HRB_HINTS),
        "has_subform": bool(norm_sub is not None),
        "trigger_value": _canon_option(q.get("trigger_value")),
        "subform": norm_sub,
    }


def _norm_structure(raw: Any) -> dict[str, Any]:
    data = _as_json(raw, {})
    sections = data.get("sections", []) if isinstance(data, dict) else []
    out = []
    for s in sections:
        out.append(
            {
                "id": str(s.get("id") or ""),
                "title": str(s.get("title") or ""),
                "order": int(s.get("order") or 0),
                "questions": [_norm_question(q) for q in s.get("questions", [])],
            }
        )
    return {"sections": out}


# --------------------------------------------------------------------------- #
# Response re-key + value cleanup (legacy data drift fixes)
# --------------------------------------------------------------------------- #
# Stored answers were keyed to an older form scheme; map them to current ids.
_PREFIX_MAP = (
    ("q_detailed_design_", "q_detailed_"),
    ("q_pre_tender_", "q_pretender_"),
    ("q_pre_construction_", "q_precon_"),
)
# Stored values vs the forms' option strings. Canonical casing comes from
# seeds.forms.EVIDENCE_OPTIONS ("Yes w/ Evidence") — the web matches options
# case-sensitively, so any drift here renders as an unanswered question.
# Looked up via s.lower(), so legacy lowercase-e variants normalise too
# (tests/test_migrate_values.py locks map outputs to the seeded options).
_VALUE_MAP = {
    "yes-(with evidence)": "Yes w/ Evidence",
    "yes-(without evidence)": "Yes w/o Evidence",
    "yes w/ evidence": "Yes w/ Evidence",
    "yes w/o evidence": "Yes w/o Evidence",
}
_BLANK_RE = re.compile(r"^[-\s]*$")  # "----------" placeholder == unanswered


def _structure_ids(structure: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for s in structure.get("sections", []):
        for q in s.get("questions", []):
            ids.add(str(q.get("id")))
            sub = q.get("subform")
            if isinstance(sub, dict):
                for sq in sub.get("questions", []):
                    ids.add(str(sq.get("id")))
    return ids


def _rekey_key(key: str) -> str:
    for old, new in _PREFIX_MAP:
        if key.startswith(old):
            return new + key[len(old):]
    return key


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if _BLANK_RE.match(s):
        return ""
    return _VALUE_MAP.get(s.lower(), s)


def _canon_option(value: Any) -> Any:
    """Canonical casing for a form option / trigger string (non-strings pass)."""
    if not isinstance(value, str):
        return value
    return _VALUE_MAP.get(value.strip().lower(), value)


def _rekey_and_clean(
    responses: dict[str, Any], valid_ids: set[str]
) -> tuple[dict[str, Any], dict[str, str]]:
    """Return (cleaned responses keyed to current form ids, orphan id->value).

    Drops blank/placeholder answers; normalises ids + values; an orphan is a
    real (non-empty) answer whose re-keyed id has no question in the form.
    """
    out: dict[str, Any] = {}
    orphans: dict[str, str] = {}
    for key, cell in responses.items():
        raw_val = cell.get("value") if isinstance(cell, dict) else cell
        val = _clean_value(raw_val)
        if not val:
            continue
        nk = _rekey_key(str(key))
        new_cell = dict(cell) if isinstance(cell, dict) else {}
        new_cell["value"] = val
        if nk not in out or not out[nk].get("value"):
            out[nk] = new_cell
        if valid_ids and nk not in valid_ids:
            orphans[nk] = val
    return out, orphans


# --------------------------------------------------------------------------- #
# Migration
# --------------------------------------------------------------------------- #
async def run() -> None:
    my = _mysql()
    cur = my.cursor()

    # ---- read legacy ----
    cur.execute("SELECT id, stage_name FROM project_qa_projectqadesignstages")
    legacy_stages = {r["id"]: r["stage_name"] for r in cur.fetchall()}

    cur.execute(
        "SELECT id, name, description, version, is_active, form_structure, "
        "stage_id, created_at, updated_at FROM project_qa_v2_form_definition"
    )
    forms = cur.fetchall()

    cur.execute(
        "SELECT id, responses, completion_percentage, total_questions, "
        "answered_questions, created_at, updated_at, form_id, last_updated_by_id, "
        "project_id, stage_id, deadline, reminder_sent_offsets "
        "FROM project_qa_v2_project_response"
    )
    responses = cur.fetchall()

    cur.execute(
        "SELECT id, description, cause_reason, action_effect, category_of_impact, "
        "discipline, created_at, updated_at, logged_by_id, project_id, stage_id "
        "FROM project_qa_v2_event_log"
    )
    events = cur.fetchall()

    cur.execute(
        "SELECT id, is_high_risk, notes, created_at, updated_at, checked_by_id, "
        "project_id, stage_id FROM project_qa_v2_high_risk_building"
    )
    hrbs = cur.fetchall()

    # projects referenced by any QA activity
    proj_ids = (
        {r["project_id"] for r in responses}
        | {r["project_id"] for r in events}
        | {r["project_id"] for r in hrbs}
    )
    proj_ids.discard(None)
    cur.execute(
        "SELECT id, number, name, sector, archived, cmap_id, director_id, manager_id "
        "FROM projects_project WHERE id IN ({})".format(
            ",".join(str(int(i)) for i in proj_ids)
        )
    )
    projects = cur.fetchall()

    # users referenced as director/manager/updater/logger/checker
    user_ids: set[int] = set()
    director_ids: set[int] = set()
    manager_ids: set[int] = set()
    for p in projects:
        if p["director_id"]:
            director_ids.add(p["director_id"])
            user_ids.add(p["director_id"])
        if p["manager_id"]:
            manager_ids.add(p["manager_id"])
            user_ids.add(p["manager_id"])
    for r in responses:
        if r["last_updated_by_id"]:
            user_ids.add(r["last_updated_by_id"])
    for r in events:
        if r["logged_by_id"]:
            user_ids.add(r["logged_by_id"])
    for r in hrbs:
        if r["checked_by_id"]:
            user_ids.add(r["checked_by_id"])
    users_rows = []
    if user_ids:
        cur.execute(
            "SELECT id, username, first_name, last_name, email FROM auth_user "
            "WHERE id IN ({})".format(",".join(str(int(i)) for i in user_ids))
        )
        users_rows = cur.fetchall()
    my.close()

    print(
        f"legacy read: {len(projects)} projects, {len(users_rows)} users, "
        f"{len(forms)} forms, {len(responses)} responses, "
        f"{len(events)} events, {len(hrbs)} hrb"
    )

    # ---- write ----
    async with SessionLocal() as session:
        # wipe QA data (keep stages); FK-safe order
        for model in (
            QaProjectResponse,
            QaEventLog,
            QaHighRiskBuilding,
            QaFormDefinition,
            Project,
            User,
        ):
            await session.execute(delete(model))
        await session.flush()

        # stages (idempotent)
        await stages_seed.seed(session)
        stage_by_order = {
            s.order: s.id
            for s in (await session.execute(select(Stage))).scalars().all()
        }
        # legacy stage id N maps to our stage order N (1..6)
        stage_map = {sid: stage_by_order.get(sid) for sid in legacy_stages}

        # users
        user_map: dict[int, Any] = {}
        seen_emails: set[str] = set()
        for u in users_rows:
            uid = u["id"]
            name = f"{u['first_name'] or ''} {u['last_name'] or ''}".strip()
            display = name or (u["username"] or f"user{uid}")
            email = (u["email"] or "").strip()
            if not email:
                email = f"{u['username'] or ('user' + str(uid))}"
            if "@" not in email:
                email = f"{email}@hts.uk.com"
            email = email.lower()
            if email in seen_emails:
                email = f"{uid}.{email}"
            seen_emails.add(email)
            roles = []
            if uid in director_ids:
                roles.append("director")
            if uid in manager_ids:
                roles.append("manager")
            if not roles:
                roles.append("engineer")
            user_obj = User(email=email, display_name=display, roles=roles)
            session.add(user_obj)
            user_map[uid] = user_obj
        await session.flush()

        # projects
        project_map: dict[int, Any] = {}
        seen_cmap: set[str] = set()
        for p in projects:
            cmap = None
            if p["cmap_id"]:
                c = str(p["cmap_id"])
                if c not in seen_cmap:
                    seen_cmap.add(c)
                    cmap = c
            director = user_map.get(p["director_id"])
            manager = user_map.get(p["manager_id"])
            project_obj = Project(
                number=str(p["number"]),
                name=p["name"] or f"Project {p['number']}",
                sector=p["sector"],
                archived=bool(p["archived"]),
                director_id=director.id if director else None,
                manager_id=manager.id if manager else None,
                cmap_ref=cmap,
            )
            session.add(project_obj)
            project_map[p["id"]] = project_obj
        await session.flush()

        # one default "Main building" per project — single-building projects use
        # it implicitly; per-building QA (responses, HRB) hangs off it.
        building_map: dict[int, Any] = {}
        for legacy_id, proj in project_map.items():
            building = Building(project_id=proj.id, name="Main building", order=0)
            session.add(building)
            building_map[legacy_id] = building
        await session.flush()

        # forms (+ keep normalised structure & valid id set for scoring)
        form_map: dict[int, Any] = {}
        form_struct: dict[int, dict[str, Any]] = {}
        form_ids: dict[int, set[str]] = {}
        for f in forms:
            structure = _norm_structure(f["form_structure"])
            sid = stage_map.get(f["stage_id"])
            if sid is None:
                continue
            form_obj = QaFormDefinition(
                name=f["name"],
                stage_id=sid,
                version=int(f["version"] or 1),
                is_active=bool(f["is_active"]),
                structure=structure,
                created_at=_utc(f["created_at"]),
                updated_at=_utc(f["updated_at"]),
            )
            session.add(form_obj)
            form_map[f["id"]] = form_obj
            form_struct[f["id"]] = structure
            form_ids[f["id"]] = _structure_ids(structure)
        await session.flush()

        # responses (re-key + clean, then recompute completion)
        order_by_stage_id = {v: k for k, v in stage_by_order.items()}
        orphans_by_stage: dict[int, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        n_resp = 0
        for r in responses:
            proj = project_map.get(r["project_id"])
            form = form_map.get(r["form_id"])
            sid = stage_map.get(r["stage_id"])
            if proj is None or form is None or sid is None:
                continue
            structure = form_struct.get(r["form_id"], {"sections": []})
            resp_json, orphans = _rekey_and_clean(
                _as_json(r["responses"], {}), form_ids.get(r["form_id"], set())
            )
            stage_order = order_by_stage_id.get(sid, 0)
            for oid in orphans:
                orphans_by_stage[stage_order][oid] += 1
            score = calculate_completion(structure, resp_json)
            updater = user_map.get(r["last_updated_by_id"])
            session.add(
                QaProjectResponse(
                    project_id=proj.id,
                    building_id=building_map[r["project_id"]].id,
                    form_id=form.id,
                    stage_id=sid,
                    responses=resp_json,
                    completion_percentage=score.completion_percentage,
                    total_questions=score.total_questions,
                    answered_questions=score.answered_questions,
                    deadline=r["deadline"],
                    reminder_sent_offsets=_as_json(r["reminder_sent_offsets"], []),
                    last_updated_by_id=updater.id if updater else None,
                    created_at=_utc(r["created_at"]),
                    updated_at=_utc(r["updated_at"]),
                )
            )
            n_resp += 1
            if n_resp % 1000 == 0:
                await session.flush()
                print(f"  ...{n_resp} responses")
        await session.flush()

        # event logs
        n_ev = 0
        for e in events:
            proj = project_map.get(e["project_id"])
            if proj is None:
                continue
            disc = _DISCIPLINES.get(str(e["discipline"]), Discipline.OTHER)
            logger = user_map.get(e["logged_by_id"])
            session.add(
                QaEventLog(
                    project_id=proj.id,
                    description=e["description"] or "",
                    cause_reason=e["cause_reason"],
                    action_effect=e["action_effect"],
                    category_of_impact=e["category_of_impact"] or "",
                    stage_id=stage_map.get(e["stage_id"]),
                    discipline=disc,
                    logged_by_id=logger.id if logger else None,
                    created_at=_utc(e["created_at"]),
                    updated_at=_utc(e["updated_at"]),
                )
            )
            n_ev += 1

        # high-risk buildings
        n_hrb = 0
        for h in hrbs:
            proj = project_map.get(h["project_id"])
            if proj is None:
                continue
            checker = user_map.get(h["checked_by_id"])
            session.add(
                QaHighRiskBuilding(
                    project_id=proj.id,
                    building_id=building_map[h["project_id"]].id,
                    stage_id=stage_map.get(h["stage_id"]),
                    is_high_risk=bool(h["is_high_risk"]),
                    checked_by_id=checker.id if checker else None,
                    notes=h["notes"],
                    created_at=_utc(h["created_at"]),
                    updated_at=_utc(h["updated_at"]),
                )
            )
            n_hrb += 1

        await session.commit()
        print(
            f"migrated: {len(user_map)} users, {len(project_map)} projects, "
            f"{len(form_map)} forms, {n_resp} responses, {n_ev} events, {n_hrb} hrb"
        )

        # Orphan report: real answers whose re-keyed id has no current form
        # question (questions removed from the forms since they were answered).
        stage_names = {
            1: "Concept", 2: "Detailed Design", 3: "Pre-tender",
            4: "Pre-construction", 5: "Site", 6: "Archive",
        }
        total_orphans = sum(
            len(ids) for ids in orphans_by_stage.values()
        )
        if total_orphans:
            print(f"\norphaned questions (kept in data, no current form home): "
                  f"{total_orphans} distinct ids")
            for order in sorted(orphans_by_stage):
                ids = orphans_by_stage[order]
                top = sorted(ids.items(), key=lambda kv: -kv[1])[:12]
                print(f"  {stage_names.get(order, order)}: {len(ids)} ids — "
                      + ", ".join(f"{k}({n})" for k, n in top))


def main() -> None:
    import asyncio

    if "DATABASE_URL" not in os.environ:
        raise SystemExit("Set DATABASE_URL to the target Postgres before running.")
    asyncio.run(run())


if __name__ == "__main__":
    main()
