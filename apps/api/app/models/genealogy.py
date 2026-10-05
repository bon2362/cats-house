from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    original_filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16))
    normalized_payload: Mapped[dict] = mapped_column(JSONB)
    counts: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    issues: Mapped[list["ImportIssue"]] = relationship(cascade="all, delete-orphan", back_populates="import_run")

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)


class Person(Base):
    __tablename__ = "people"
    __table_args__ = (UniqueConstraint("import_run_id", "source_uid", name="uq_people_import_source_uid"),)

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    import_run_id: Mapped[UUID] = mapped_column(ForeignKey("import_runs.id"))
    display_name: Mapped[str] = mapped_column(String(512))
    source_uid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sex: Mapped[str | None] = mapped_column(String(32), nullable=True)
    biography: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(default=False, server_default="false")


class Union(Base):
    __tablename__ = "unions"

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    import_run_id: Mapped[UUID] = mapped_column(ForeignKey("import_runs.id"))
    partner_one_id: Mapped[UUID | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    partner_two_id: Mapped[UUID | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    union_type: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ParentChild(Base):
    __tablename__ = "parent_children"
    __table_args__ = (UniqueConstraint("parent_id", "child_id", "relationship_type", name="uq_parent_child_type"),)

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    parent_id: Mapped[UUID] = mapped_column(ForeignKey("people.id"))
    child_id: Mapped[UUID] = mapped_column(ForeignKey("people.id"))
    union_id: Mapped[UUID | None] = mapped_column(ForeignKey("unions.id"), nullable=True)
    relationship_type: Mapped[str] = mapped_column(String(32), default="biological")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    person_id: Mapped[UUID | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    union_id: Mapped[UUID | None] = mapped_column(ForeignKey("unions.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64))
    date_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_qualifier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    date_lower: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    date_upper: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    place: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    body: Mapped[str] = mapped_column(Text)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(512))


class Media(Base):
    __tablename__ = "media"
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    storage_key: Mapped[str] = mapped_column(String(1024))
    media_type: Mapped[str] = mapped_column(String(32))
    original_filename: Mapped[str] = mapped_column(String(255), default="")
    is_published: Mapped[bool] = mapped_column(default=False, server_default="false")


class MediaLink(Base):
    __tablename__ = "media_links"

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    media_id: Mapped[UUID] = mapped_column(ForeignKey("media.id"))
    person_id: Mapped[UUID | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    event_id: Mapped[UUID | None] = mapped_column(ForeignKey("events.id"), nullable=True)


class ImportIssue(Base):
    __tablename__ = "import_issues"

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    import_run_id: Mapped[UUID] = mapped_column(ForeignKey("import_runs.id"))
    severity: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tag: Mapped[str | None] = mapped_column(String(32), nullable=True)
    import_run: Mapped[ImportRun] = relationship(back_populates="issues")


class ChangeLog(Base):
    __tablename__ = "change_logs"

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True))
    owner_email: Mapped[str] = mapped_column(String(255))
    before: Mapped[dict] = mapped_column(JSONB)
    after: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
