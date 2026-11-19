"""API 请求和响应结构。"""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=180)
    lead_economy: str
    partner_economies: list[str] = Field(min_length=1, max_length=20)
    sector: str
    coordinator: str
    source_ref: str
    opened_on: date


class EventImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_system: str = Field(min_length=1, max_length=80)
    records: list[dict[str, Any]] = Field(min_length=1, max_length=500)


class ErrorBody(BaseModel):
    detail: Any


class Health(BaseModel):
    status: str
    service: str
