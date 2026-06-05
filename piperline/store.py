"""Persistence — SQLite-backed store for JobPosts and Applications.

Design: the pydantic contracts (common/models.py) remain the source of truth.
We store each record's full JSON blob plus a few promoted columns we query/filter
on (status, job_id, fit_score). This keeps the schema trivially compatible with
contract changes — add a field to the model, no migration needed.

Idempotency lives here: jobs and applications are keyed by their stable id, so
re-running discovery never creates duplicates.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Column,
    Float,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Session

from piperline.common import Application, Event, JobPost


class Base(DeclarativeBase):
    pass


class JobRow(Base):
    __tablename__ = "jobs"
    id = Column(String, primary_key=True)
    source = Column(String, index=True)
    title = Column(String)
    company = Column(String)
    data = Column(Text, nullable=False)  # JobPost JSON


class AppRow(Base):
    __tablename__ = "applications"
    id = Column(String, primary_key=True)
    job_id = Column(String, index=True, unique=True)  # one application per job
    status = Column(String, index=True)
    fit_score = Column(Float)
    data = Column(Text, nullable=False)  # Application JSON


class Store:
    """Thin repository over SQLite. One instance per run is fine."""

    def __init__(self, db_path: Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}", future=True)
        Base.metadata.create_all(self.engine)

    # --- jobs ------------------------------------------------------------
    def upsert_job(self, job: JobPost) -> bool:
        """Insert the job if new. Returns True if it was new, False if it existed."""
        with Session(self.engine) as s:
            existing = s.get(JobRow, job.id)
            if existing:
                return False
            s.add(JobRow(
                id=job.id, source=job.source, title=job.title,
                company=job.company, data=job.model_dump_json(),
            ))
            s.commit()
            return True

    def get_job(self, job_id: str) -> JobPost | None:
        with Session(self.engine) as s:
            row = s.get(JobRow, job_id)
            return JobPost.model_validate_json(row.data) if row else None

    # --- applications ----------------------------------------------------
    def get_application(self, job_id: str) -> Application | None:
        with Session(self.engine) as s:
            row = s.scalar(select(AppRow).where(AppRow.job_id == job_id))
            return Application.model_validate_json(row.data) if row else None

    def save_application(self, app: Application) -> None:
        with Session(self.engine) as s:
            row = s.get(AppRow, app.id)
            payload = dict(
                id=app.id, job_id=app.job_id, status=app.status,
                fit_score=app.fit_score, data=app.model_dump_json(),
            )
            if row:
                for k, v in payload.items():
                    setattr(row, k, v)
            else:
                s.add(AppRow(**payload))
            s.commit()

    def list_applications(
        self, *, status: str | None = None
    ) -> list[Application]:
        with Session(self.engine) as s:
            stmt = select(AppRow)
            if status:
                stmt = stmt.where(AppRow.status == status)
            stmt = stmt.order_by(AppRow.fit_score.desc().nullslast())
            return [Application.model_validate_json(r.data) for r in s.scalars(stmt)]

    def status_counts(self) -> dict[str, int]:
        with Session(self.engine) as s:
            counts: dict[str, int] = {}
            for row in s.scalars(select(AppRow)):
                counts[row.status] = counts.get(row.status, 0) + 1
            return counts


def advance(app: Application, status, note: str = "") -> Application:
    """Move an application to a new status and append an audit event.

    Pure helper (no DB) so callers control when to persist. Uses an injected
    timestamp-free Event by stamping now() here; callers persist via save_application.
    """
    app.status = status
    app.history.append(Event(at=datetime.now(), status=status, note=note))
    return app
