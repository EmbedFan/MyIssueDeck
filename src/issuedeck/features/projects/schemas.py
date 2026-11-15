"""Pydantic DTOs for the projects feature."""

from __future__ import annotations

from pydantic import BaseModel

from issuedeck.core.config import BranchConfig, KindConfig, StatusConfig


class ProjectSummary(BaseModel):
    key: str
    name: str
    description: str
    item_count: int


class ProjectList(BaseModel):
    projects: list[ProjectSummary]


class TimeSummary(BaseModel):
    project_key: str
    unit: str = "hours"
    estimated_time: float
    time_spent: float


class ProjectDetail(BaseModel):
    key: str
    name: str
    description: str
    kinds: dict[str, KindConfig]
    statuses: dict[str, StatusConfig]
    branches: list[BranchConfig]
