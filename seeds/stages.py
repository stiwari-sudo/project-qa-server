from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stage import Stage
from app.repositories import stages as stages_repo

# The six QA design stages, in order.
STAGES: list[tuple[int, str]] = [
    (1, "Concept"),
    (2, "Detailed Design"),
    (3, "Pre-tender"),
    (4, "Pre-construction"),
    (5, "Site"),
    (6, "Archive"),
]


async def seed(session: AsyncSession) -> None:
    existing = {s.order for s in await stages_repo.list_ordered(session)}
    for order, name in STAGES:
        if order in existing:
            continue
        session.add(Stage(name=name, order=order))
    await session.flush()
