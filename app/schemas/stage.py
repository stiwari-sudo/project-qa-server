from __future__ import annotations

import uuid

from app.schemas.common import OrmBase


class StageOut(OrmBase):
    id: uuid.UUID
    name: str
    order: int
