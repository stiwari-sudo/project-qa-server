from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import can_view_all_projects
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models.user import User
from app.repositories import project_members as members_repo
from app.repositories import projects as projects_repo
from app.repositories import users as users_repo
from app.schemas.user import UserOut


async def list_members(
    session: AsyncSession, project_id: uuid.UUID
) -> list[UserOut]:
    if await projects_repo.get_by_id(session, project_id) is None:
        raise NotFoundError("Project not found")
    rows = await members_repo.list_members(session, project_id)
    return [UserOut.model_validate(u) for u in rows]


async def add_member(
    session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID
) -> UserOut:
    if await projects_repo.get_by_id(session, project_id) is None:
        raise NotFoundError("Project not found")
    user = await users_repo.get_by_id(session, user_id)
    if user is None:
        raise NotFoundError("User not found")
    # Idempotent: adding an existing member is a no-op for a smooth admin UX.
    if await members_repo.get(session, project_id, user_id) is None:
        await members_repo.add(session, project_id, user_id)
    return UserOut.model_validate(user)


async def remove_member(
    session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    if not await members_repo.remove(session, project_id, user_id):
        raise NotFoundError("User is not a member of this project")


async def visible_project_ids(
    session: AsyncSession, user: User
) -> set[uuid.UUID] | None:
    """The set of project ids the user may see, or ``None`` for "no restriction"
    (view-all roles). Engineers are limited to projects they're a member of."""
    if can_view_all_projects(user):
        return None
    return set(await members_repo.list_project_ids_for_user(session, user.id))


async def member_project_ids(session: AsyncSession, user: User) -> set[uuid.UUID]:
    """Projects the user is explicitly assigned to, regardless of role — backs
    the personal "My Dashboard" (so a view-all user still sees only their own)."""
    return set(await members_repo.list_project_ids_for_user(session, user.id))


async def assert_can_view_project(
    session: AsyncSession, user: User, project_id: uuid.UUID
) -> None:
    """Raise 403 if an own-only user tries to reach a project they aren't a
    member of. No-op for view-all users."""
    if can_view_all_projects(user):
        return
    if await members_repo.get(session, project_id, user.id) is None:
        raise PermissionDeniedError("You don't have access to this project")
