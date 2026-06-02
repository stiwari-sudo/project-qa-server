from __future__ import annotations

from fastapi import APIRouter

from app.routers import (
    event_logs,
    forms,
    hrb,
    overview,
    projects,
    responses,
    stages,
    stats,
    users,
)

api_router = APIRouter()
api_router.include_router(users.router)
api_router.include_router(stages.router)
api_router.include_router(forms.router)
api_router.include_router(projects.router)
api_router.include_router(responses.router)
api_router.include_router(stats.router)
api_router.include_router(overview.router)
api_router.include_router(event_logs.router)
api_router.include_router(hrb.router)

__all__ = ["api_router"]
