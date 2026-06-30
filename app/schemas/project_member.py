from __future__ import annotations

import uuid

from pydantic import BaseModel


class MemberAdd(BaseModel):
    """Add a user to a project's visibility list."""

    user_id: uuid.UUID
