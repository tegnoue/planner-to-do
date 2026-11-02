import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    supersedes_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, unique=True)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="todo")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recurrence_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    recurrence_dtstart: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recurrence_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recurrence_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
    subtasks: Mapped[list["Task"]] = relationship(back_populates="parent", cascade="all, delete-orphan", foreign_keys=[parent_task_id])
    parent: Mapped["Task | None"] = relationship(back_populates="subtasks", remote_side=[id], foreign_keys=[parent_task_id])
    tags: Mapped[list["Tag"]] = relationship(secondary="task_tags", back_populates="tasks")


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    color: Mapped[str] = mapped_column(String(20), default="#64748b")
    tasks: Mapped[list[Task]] = relationship(secondary="task_tags", back_populates="tags")


class TaskTag(Base):
    __tablename__ = "task_tags"
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class TaskSchedule(Base):
    __tablename__ = "task_schedules"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    planned_date: Mapped[date] = mapped_column(Date)
    planned_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class TaskOccurrence(Base):
    __tablename__ = "task_occurrences"
    __table_args__ = (UniqueConstraint("task_id", "recurrence_key", name="uq_occurrence_task_key"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    recurrence_key: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at_override: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_override: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_override: Mapped[str | None] = mapped_column(String(240), nullable=True)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
