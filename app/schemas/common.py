from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Paginated(BaseModel, Generic[T]):
    count: int
    page: int
    page_size: int
    total_pages: int
    results: list[T]
