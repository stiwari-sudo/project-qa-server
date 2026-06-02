from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class Stage(UUIDPkMixin, TimestampMixin, Base):
    """One of the six QA design stages (order 1..6)."""

    __tablename__ = "stages"

    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    order: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Stage {self.order}:{self.name}>"
