"""SQLite 连接、迁移和事务边界。"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  lead_economy TEXT NOT NULL,
  partner_economies TEXT NOT NULL,
  sector TEXT NOT NULL,
  coordinator TEXT NOT NULL,
  source_ref TEXT NOT NULL UNIQUE,
  opened_on TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  source_system TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK(revision > 0),
  kind TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  received_at TEXT NOT NULL,
  payload TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  UNIQUE(source_system, source_record_id, revision)
);
CREATE INDEX IF NOT EXISTS observation_project_time
  ON observations(project_id, occurred_at, source_record_id, revision);
CREATE INDEX IF NOT EXISTS observation_source
  ON observations(source_system, source_record_id, revision);
CREATE TABLE IF NOT EXISTS import_batches (
  id TEXT PRIMARY KEY,
  source_system TEXT NOT NULL,
  received_at TEXT NOT NULL,
  record_count INTEGER NOT NULL,
  accepted_count INTEGER NOT NULL,
  duplicate_count INTEGER NOT NULL,
  digest TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS batch_items (
  batch_id TEXT NOT NULL REFERENCES import_batches(id),
  ordinal INTEGER NOT NULL,
  observation_id TEXT,
  disposition TEXT NOT NULL,
  detail TEXT NOT NULL,
  PRIMARY KEY(batch_id, ordinal)
);
"""


class Database:
    def __init__(self, path: str | Path = "bridgeboard.sqlite3") -> None:
        self.path = str(path)
        self._initialized = False

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        if self.path != ":memory:":
            connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        if self._initialized:
            return
        connection = self.connect()
        try:
            connection.executescript(SCHEMA)
            self._initialized = True
        finally:
            connection.close()

    @contextmanager
    def transaction(self, immediate: bool = True) -> Iterator[sqlite3.Connection]:
        self.initialize()
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def read(self) -> sqlite3.Connection:
        self.initialize()
        return self.connect()
