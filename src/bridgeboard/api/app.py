"""FastAPI 装配与 HTTP 边界。"""

import os
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from bridgeboard.analytics.service import AnalyticsService
from bridgeboard.api.schemas import EventImport, ProjectCreate
from bridgeboard.domain.errors import BatchRejected, BridgeboardError
from bridgeboard.domain.catalog import build_catalog
from bridgeboard.intake.service import IntakeService
from bridgeboard.portfolio.database import Database
from bridgeboard.portfolio.history import HistoryService
from bridgeboard.portfolio.service import PortfolioService


def create_app(database: Database | None = None) -> FastAPI:
    selected = database or Database(os.environ.get("BRIDGEBOARD_DB", "bridgeboard.sqlite3"))
    selected.initialize()
    portfolio = PortfolioService(selected)
    intake = IntakeService(selected)
    analytics = AnalyticsService(selected)
    history = HistoryService(selected)
    app = FastAPI(title="亚太合作项目分析服务", version="1.0.0")
    app.state.database = selected

    @app.exception_handler(BatchRejected)
    async def batch_rejected(_: Request, error: BatchRejected):
        return JSONResponse(status_code=422,
                            content={"detail": "导入批次未写入", "issues": error.issues})

    @app.exception_handler(BridgeboardError)
    async def business_error(_: Request, error: BridgeboardError):
        status = 404 if error.__class__.__name__ == "NotFound" else 409
        if error.__class__.__name__ == "InvalidInput":
            status = 422
        return JSONResponse(status_code=status, content={"detail": str(error)})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "bridgeboard"}

    @app.get("/catalog")
    def catalog() -> dict[str, Any]:
        return build_catalog()

    @app.post("/projects", status_code=201)
    def create_project(body: ProjectCreate) -> dict[str, Any]:
        return portfolio.create_project(body.model_dump(mode="json"))

    @app.get("/projects")
    def list_projects(sector: str | None = None,
                      economy: str | None = None) -> list[dict[str, Any]]:
        return portfolio.list_projects(sector, economy)

    @app.get("/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        return portfolio.get_project(project_id)

    @app.get("/projects/{project_id}/history")
    def project_history(project_id: str) -> dict[str, Any]:
        return history.project_history(project_id)

    @app.post("/imports/events", status_code=201)
    def import_events(body: EventImport) -> dict[str, Any]:
        return intake.import_events(body.source_system, body.records)

    @app.get("/analytics/portfolio")
    def portfolio_report(
        as_of: date | None = None,
        sector: str | None = None,
        economy: str | None = None,
        opened_from: date | None = None,
        opened_to: date | None = None,
        stale_after_days: int = Query(default=90, ge=1, le=3650),
    ) -> dict[str, Any]:
        return analytics.report(as_of=as_of, sector=sector, economy=economy,
                                opened_from=opened_from, opened_to=opened_to,
                                stale_after_days=stale_after_days)

    @app.get("/analytics/sources")
    def source_report(as_of: date | None = None) -> dict[str, Any]:
        return analytics.source_quality(as_of=as_of)

    @app.get("/analytics/followups")
    def followup_report(
        as_of: date | None = None,
        stale_after_days: int = Query(default=90, ge=1, le=3650),
    ) -> dict[str, Any]:
        return analytics.followups(as_of=as_of, stale_after_days=stale_after_days)

    @app.get("/imports/batches/{batch_id}")
    def get_import_batch(batch_id: str) -> dict[str, Any]:
        from bridgeboard.portfolio.repository import get_batch
        connection = selected.read()
        try:
            return get_batch(connection, batch_id)
        finally:
            connection.close()

    return app


app = create_app()
