"""把组合筛选、事实投影和指标解释组合为只读查询。"""

from datetime import date, datetime, timezone
from typing import Any

from bridgeboard.analytics.report import build_report
from bridgeboard.analytics.source_quality import build_source_quality
from bridgeboard.analytics.followups import build_followups
from bridgeboard.domain.model import ECONOMIES, SECTORS
from bridgeboard.portfolio import repository
from bridgeboard.portfolio.database import Database


class AnalyticsService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def report(self, *, as_of: date | None = None,
               sector: str | None = None, economy: str | None = None,
               opened_from: date | None = None,
               opened_to: date | None = None,
               stale_after_days: int = 90) -> dict[str, Any]:
        _check_filter(sector, SECTORS, "sector")
        _check_filter(economy, ECONOMIES, "economy")
        connection = self.database.read()
        try:
            projects = repository.list_projects(connection)
            events = repository.all_observations(connection)
            batches = repository.all_batches(connection)
        finally:
            connection.close()
        current = as_of or datetime.now(timezone.utc).date()
        return build_report(projects, events, as_of=current, sector=sector,
                            economy=economy, opened_from=opened_from,
                            opened_to=opened_to,
                            stale_after_days=stale_after_days)

    def source_quality(self, *, as_of: date | None = None) -> dict[str, Any]:
        connection = self.database.read()
        try:
            events = repository.all_observations(connection)
            batches = repository.all_batches(connection)
        finally:
            connection.close()
        current = as_of or datetime.now(timezone.utc).date()
        return build_source_quality(events, batches, as_of=current)

    def followups(self, *, as_of: date | None = None,
                  stale_after_days: int = 90) -> dict[str, Any]:
        connection = self.database.read()
        try:
            projects = repository.list_projects(connection)
            events = repository.all_observations(connection)
        finally:
            connection.close()
        current = as_of or datetime.now(timezone.utc).date()
        return build_followups(projects, events, as_of=current,
                               stale_after_days=stale_after_days)


def _check_filter(value: str | None, options: set[str], field: str) -> None:
    if value is not None and value not in options:
        from bridgeboard.domain.errors import InvalidInput
        raise InvalidInput(f"{field} 不在当前业务目录中")
