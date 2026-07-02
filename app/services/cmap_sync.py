"""Daily CMAP sync: pull users + projects from CMap and upsert them.

CMap is authoritative for the user list, their roles, and the project list
(MSAL only authenticates login — see app/auth/azure.py). This runs on a
schedule (Windows Task Scheduler on the J:-VM) via scripts/run_cmap_sync.py.

Field names across CMap's API are matched case-insensitively against a set of
candidate keys, so the exact casing is confirmed on the first --dry-run (which
prints the raw record keys) without code changes. Roles come from CMap via the
CMAP_ROLE_MAP setting; a CMap role with no mapping grants NO role (fail closed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.project import Project
from app.models.user import User
from app.repositories import projects as projects_repo
from app.repositories import users as users_repo
from app.services.cmap_client import CmapClient

logger = get_logger(__name__)

# Candidate keys (matched case-insensitively) for each field we need. Order =
# preference. Extend here once the live --dry-run confirms CMap's real names.
_USER_ID = ("id", "userId", "userGuid", "guid")
_USER_EMAIL = ("email", "emailAddress", "workEmail", "userName", "username")
_USER_FULLNAME = ("fullName", "displayName", "name")
_USER_FIRST = ("firstName", "forename", "givenName")
_USER_LAST = ("lastName", "surname", "familyName")
_USER_ACTIVE = ("isActive", "active", "isEnabled", "enabled")
_USER_INACTIVE = ("isDisabled", "disabled", "isDeleted", "deleted", "isLeaver", "hasLeft")
_USER_ROLE = ("securityGroup", "role", "userRole", "jobTitle", "position")

_PROJECT_ID = ("id", "projectId", "projectGuid", "guid")
_PROJECT_NUMBER = (
    "code", "projectCode", "reference", "projectReference",
    "projectNumber", "number", "jobNumber",
)
_PROJECT_NAME = ("name", "projectName", "title", "projectTitle")
_PROJECT_STAGE = ("stage", "projectStage", "status", "projectStatus", "phase")
_PROJECT_DIRECTOR = ("projectDirector", "director", "projectDirectorId", "directorId")
_PROJECT_MANAGER = (
    "projectManager", "manager", "projectLead", "lead",
    "projectManagerId", "managerId", "projectLeadId",
)
_PERSON_REF = ("id", "userId", "guid", "email", "emailAddress")


def _index(record: dict[str, Any]) -> dict[str, Any]:
    """Lowercased-key view of a record (first key wins on collision)."""
    out: dict[str, Any] = {}
    for key, value in record.items():
        low = key.lower()
        if low not in out:
            out[low] = value
    return out


def _first(indexed: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = indexed.get(key.lower())
        if value is not None and value != "":
            return value
    return None


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "y", "active", "enabled"):
        return True
    if text in ("false", "0", "no", "n", "inactive", "disabled"):
        return False
    return default


def _person_ref(value: Any) -> str | None:
    """A comparable reference (CMap user id or email) for a director/manager
    field that may be a bare id/email or a nested person object."""
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        inner = _first(_index(value), _PERSON_REF)
        return str(inner) if inner is not None else None
    return str(value)


@dataclass
class MappedUser:
    cmap_id: str | None
    email: str | None
    name: str
    is_active: bool
    cmap_role: str | None


@dataclass
class MappedProject:
    cmap_id: str | None
    number: str | None
    name: str
    stage: str | None
    director_ref: str | None
    manager_ref: str | None


def map_user(record: dict[str, Any]) -> MappedUser:
    ci = _index(record)
    raw_email = _first(ci, _USER_EMAIL)
    email = str(raw_email).strip().lower() if raw_email else None

    full = _first(ci, _USER_FULLNAME)
    if full:
        name = str(full).strip()
    else:
        parts = [_first(ci, _USER_FIRST), _first(ci, _USER_LAST)]
        name = " ".join(str(p) for p in parts if p).strip()

    cid = _first(ci, _USER_ID)
    active = _as_bool(_first(ci, _USER_ACTIVE), default=True)
    inactive = _as_bool(_first(ci, _USER_INACTIVE), default=False)
    role = _first(ci, _USER_ROLE)
    return MappedUser(
        cmap_id=str(cid) if cid is not None else None,
        email=email,
        name=name or (email or ""),
        is_active=active and not inactive,
        cmap_role=str(role).strip() if role else None,
    )


def map_project(record: dict[str, Any]) -> MappedProject:
    ci = _index(record)
    cid = _first(ci, _PROJECT_ID)
    number = _first(ci, _PROJECT_NUMBER)
    name = _first(ci, _PROJECT_NAME)
    stage = _first(ci, _PROJECT_STAGE)
    return MappedProject(
        cmap_id=str(cid) if cid is not None else None,
        number=str(number).strip() if number else None,
        name=str(name).strip() if name else "",
        stage=str(stage).strip() if stage else None,
        director_ref=_person_ref(_first(ci, _PROJECT_DIRECTOR)),
        manager_ref=_person_ref(_first(ci, _PROJECT_MANAGER)),
    )


def resolve_role(cmap_role: str | None, role_map: dict[str, str]) -> list[str]:
    """Our QA role(s) for a CMap role name — [] when unmapped (fail closed)."""
    if not cmap_role:
        return []
    mapped = role_map.get(cmap_role.strip().lower())
    return [mapped] if mapped else []


def _resolve_person(
    ref: str | None,
    by_cmap_id: dict[str, User],
    by_email: dict[str, User],
) -> Any:
    if not ref:
        return None
    user = by_cmap_id.get(ref)
    if user is None and "@" in ref:
        user = by_email.get(ref.strip().lower())
    return user.id if user is not None else None


@dataclass
class SyncSummary:
    users_seen: int = 0
    users_created: int = 0
    users_updated: int = 0
    users_skipped: int = 0
    projects_seen: int = 0
    projects_created: int = 0
    projects_updated: int = 0
    projects_skipped: int = 0
    unresolved_people: int = 0
    sample_user_keys: list[str] = field(default_factory=list)
    sample_project_keys: list[str] = field(default_factory=list)
    dry_run: bool = False


async def run_sync(
    session: AsyncSession,
    *,
    client: CmapClient | None = None,
    dry_run: bool = False,
    limit: int | None = None,
) -> SyncSummary:
    """Fetch CMap users + projects and upsert them. On dry_run the transaction
    is rolled back and the record keys are surfaced so the field mapping can be
    confirmed before writing anything."""
    client = client or CmapClient()
    role_map = settings.cmap_role_map_parsed
    summary = SyncSummary(dry_run=dry_run)

    users_raw = await client.get_all("/v1/Users", limit=limit)
    if users_raw:
        summary.sample_user_keys = sorted(users_raw[0].keys())

    by_cmap_id: dict[str, User] = {}
    by_email: dict[str, User] = {}
    for record in users_raw:
        summary.users_seen += 1
        mapped = map_user(record)
        if not mapped.email:
            summary.users_skipped += 1
            continue
        roles = resolve_role(mapped.cmap_role, role_map)
        user = await users_repo.get_by_email(session, mapped.email)
        if user is None:
            user = await users_repo.create(
                session,
                email=mapped.email,
                display_name=mapped.name or mapped.email,
                roles=roles,
            )
            summary.users_created += 1
        else:
            if mapped.name:
                user.display_name = mapped.name
            user.roles = roles  # CMap is authoritative for roles (handles revocation)
            summary.users_updated += 1
        user.is_active = mapped.is_active
        if mapped.cmap_id:
            by_cmap_id[mapped.cmap_id] = user
        by_email[mapped.email] = user

    projects_raw = await client.get_all("/v1/Projects", limit=limit)
    if projects_raw:
        summary.sample_project_keys = sorted(projects_raw[0].keys())

    for record in projects_raw:
        summary.projects_seen += 1
        mp = map_project(record)
        if not (mp.cmap_id or mp.number):
            summary.projects_skipped += 1
            continue

        project: Project | None = None
        if mp.cmap_id:
            project = await projects_repo.get_by_cmap_ref(session, mp.cmap_id)
        if project is None and mp.number:
            project = await projects_repo.get_by_number(session, mp.number)

        director_id = _resolve_person(mp.director_ref, by_cmap_id, by_email)
        manager_id = _resolve_person(mp.manager_ref, by_cmap_id, by_email)
        if mp.director_ref and director_id is None:
            summary.unresolved_people += 1
        if mp.manager_ref and manager_id is None:
            summary.unresolved_people += 1

        if project is None:
            session.add(
                Project(
                    number=mp.number or mp.cmap_id or "",
                    name=mp.name or mp.number or "Unnamed",
                    cmap_ref=mp.cmap_id,
                    cmap_stage=mp.stage,
                    director_id=director_id,
                    manager_id=manager_id,
                )
            )
            summary.projects_created += 1
        else:
            if mp.name:
                project.name = mp.name
            if mp.cmap_id and not project.cmap_ref:
                project.cmap_ref = mp.cmap_id
            project.cmap_stage = mp.stage
            if director_id is not None:
                project.director_id = director_id
            if manager_id is not None:
                project.manager_id = manager_id
            summary.projects_updated += 1

    if dry_run:
        await session.rollback()
    else:
        await session.commit()
    logger.info("cmap.sync.complete", **summary.__dict__)
    return summary
