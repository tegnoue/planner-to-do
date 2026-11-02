from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Status = Literal["todo", "in_progress", "done"]
Priority = Literal["urgent", "medium", "low"]


class RecurrenceCreate(BaseModel):
    rrule: str = Field(min_length=5, max_length=500)
    dtstart: datetime
    timezone: str = "UTC"


class TaskCreate(BaseModel):
    kind: Literal["single", "recurring"] = "single"
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    status: Status = "todo"
    priority: Priority = "medium"
    due_at: datetime | None = None
    recurrence: RecurrenceCreate | None = None
    parent_task_id: UUID | None = None
    tag_ids: list[UUID] = []

    @model_validator(mode="after")
    def validate_kind(self):
        if self.kind == "recurring" and self.recurrence is None:
            raise ValueError("recurrence é obrigatório para tarefa recorrente")
        if self.kind == "single" and self.recurrence is not None:
            raise ValueError("recurrence só pode ser enviado para tarefa recorrente")
        return self


class RecurrenceRead(RecurrenceCreate):
    ends_at: datetime | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    kind: Literal["single", "recurring"]
    title: str
    description: str | None
    status: Status
    priority: Priority
    due_at: datetime | None
    parent_task_id: UUID | None
    tag_ids: list[UUID]
    recurrence: RecurrenceRead | None
    supersedes_task_id: UUID | None
    created_at: datetime


class TaskStatusUpdate(BaseModel):
    status: Status


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = None
    priority: Priority | None = None
    due_at: datetime | None = None
    tag_ids: list[UUID] | None = None


class RecurrenceReplace(BaseModel):
    effective_from: datetime
    new_recurrence: RecurrenceCreate
    copy: dict[str, bool] = {"title": True, "description": True, "priority": True, "tag_ids": True}


class OccurrenceUpdate(BaseModel):
    status: Status | None = None
    priority: Priority | None = None
    due_at: datetime | None = None
    description: str | None = None
    title: str | None = None
    is_cancelled: bool | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("Envie ao menos um campo para alteração")
        return self


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    color: str = "#64748b"


class ScheduleCreate(BaseModel):
    planned_date: date
    planned_minutes: int | None = Field(default=None, ge=1)
    notes: str | None = None
