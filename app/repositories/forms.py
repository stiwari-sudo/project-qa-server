from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.form import QaFormDefinition


async def list_active(session: AsyncSession) -> Sequence[QaFormDefinition]:
    result = await session.execute(
        select(QaFormDefinition)
        .where(QaFormDefinition.is_active.is_(True))
        .options(selectinload(QaFormDefinition.stage))
        .order_by(QaFormDefinition.name)
    )
    return result.scalars().all()


async def get_active_by_stage(
    session: AsyncSession, stage_id: uuid.UUID
) -> QaFormDefinition | None:
    """Latest active form version for a stage."""
    result = await session.execute(
        select(QaFormDefinition)
        .where(
            QaFormDefinition.stage_id == stage_id,
            QaFormDefinition.is_active.is_(True),
        )
        .options(selectinload(QaFormDefinition.stage))
        .order_by(QaFormDefinition.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_by_id(
    session: AsyncSession, form_id: uuid.UUID
) -> QaFormDefinition | None:
    result = await session.execute(
        select(QaFormDefinition)
        .where(QaFormDefinition.id == form_id)
        .options(selectinload(QaFormDefinition.stage))
    )
    return result.scalar_one_or_none()


async def create(
    session: AsyncSession,
    *,
    name: str,
    stage_id: uuid.UUID,
    version: int,
    is_active: bool,
    structure: dict[str, Any],
) -> QaFormDefinition:
    form = QaFormDefinition(
        name=name,
        stage_id=stage_id,
        version=version,
        is_active=is_active,
        structure=structure,
    )
    session.add(form)
    await session.flush()
    await session.refresh(form, attribute_names=["stage"])
    return form
