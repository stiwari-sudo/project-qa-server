"""SQLAlchemy models. Importing this package registers all tables on Base.metadata."""

from __future__ import annotations

from app.models.base import Base
from app.models.building import Building
from app.models.building_control import QaBuildingControl
from app.models.event_log import Discipline, QaEventLog
from app.models.form import QaFormDefinition
from app.models.hrb import QaHighRiskBuilding
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.response import QaProjectResponse
from app.models.stage import Stage
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Project",
    "ProjectMember",
    "Building",
    "Stage",
    "QaFormDefinition",
    "QaProjectResponse",
    "QaEventLog",
    "Discipline",
    "QaHighRiskBuilding",
    "QaBuildingControl",
]
