from __future__ import annotations

import uuid

from app.schemas.common import OrmBase


class UserOut(OrmBase):
    id: uuid.UUID
    email: str
    display_name: str
    roles: list[str]
    is_active: bool
