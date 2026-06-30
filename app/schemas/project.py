from __future__ import annotations

import uuid

from app.schemas.common import OrmBase


class ProjectOut(OrmBase):
    id: uuid.UUID
    number: str
    name: str
    sector: str | None = None
    archived: bool
    director_id: uuid.UUID | None = None
    director_name: str | None = None
    manager_id: uuid.UUID | None = None
    manager_name: str | None = None
    cmap_stage: str | None = None
