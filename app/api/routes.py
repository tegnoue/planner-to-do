from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.models import Task, TaskOccurrence, TaskSchedule, Tag
from app.schemas import (OccurrenceUpdate, RecurrenceReplace, ScheduleCreate, TagCreate,
                         TaskCreate, TaskRead, TaskStatusUpdate, TaskUpdate)
from app.services import resolve_tags, rule_for, serialize_task, validate_recurrence

router = APIRouter(prefix="/api/v1")


def get_task(db: Session, task_id: UUID) -> Task:
    task = db.scalar(select(Task).options(selectinload(Task.tags)).where(Task.id == task_id))
    if task is None:
        raise HTTPException(404, "Tarefa não encontrada")
    return task


@router.post("/tasks", response_model=TaskRead, status_code=201)
def create_task(payload: TaskCreate, response: Response, db: Session = Depends(get_db)):
    task = Task(title=payload.title, description=payload.description, status=payload.status,
                priority=payload.priority, due_at=payload.due_at, parent_task_id=payload.parent_task_id,
                tags=resolve_tags(db, payload.tag_ids))
    if payload.recurrence:
        start = validate_recurrence(payload.recurrence.rrule, payload.recurrence.dtstart, payload.recurrence.timezone)
        task.recurrence_rule = payload.recurrence.rrule
        task.recurrence_dtstart = start
        task.recurrence_timezone = payload.recurrence.timezone
    if task.parent_task_id:
        parent = db.get(Task, task.parent_task_id)
        if not parent:
            raise HTTPException(404, "Tarefa pai não encontrada")
        if parent.parent_task_id:
            raise HTTPException(422, "Subtarefas podem ter apenas um nível")
    db.add(task)
    db.commit()
    db.refresh(task)
    return serialize_task(get_task(db, task.id))


@router.get("/tasks", response_model=list[TaskRead])
def list_tasks(db: Session = Depends(get_db)):
    tasks = db.scalars(select(Task).options(selectinload(Task.tags)).order_by(Task.created_at.desc())).all()
    return [serialize_task(task) for task in tasks]


@router.patch("/tasks/{task_id}/status", response_model=TaskRead)
def update_task_status(task_id: UUID, payload: TaskStatusUpdate, db: Session = Depends(get_db)):
    task = get_task(db, task_id)
    task.status = payload.status
    db.commit()
    return serialize_task(get_task(db, task_id))


@router.patch("/tasks/{task_id}", response_model=TaskRead)
def edit_task(task_id: UUID, payload: TaskUpdate, db: Session = Depends(get_db)):
    task = get_task(db, task_id)
    changes = payload.model_dump(exclude_unset=True)
    if "tag_ids" in changes:
        task.tags = resolve_tags(db, changes.pop("tag_ids") or [])
    for field, value in changes.items():
        setattr(task, field, value)
    db.commit()
    return serialize_task(get_task(db, task_id))


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: UUID, db: Session = Depends(get_db)):
    task = get_task(db, task_id)
    db.delete(task)
    db.commit()
    return Response(status_code=204)


@router.patch("/tasks/{task_id}/recurrence", status_code=201)
def replace_recurrence(task_id: UUID, payload: RecurrenceReplace, db: Session = Depends(get_db)):
    old = get_task(db, task_id)
    if not old.recurrence_rule:
        raise HTTPException(409, "A tarefa não é uma série recorrente")
    if old.recurrence_ends_at:
        raise HTTPException(409, "A série já foi encerrada")
    if payload.effective_from <= old.recurrence_dtstart:
        raise HTTPException(422, "effective_from deve ser posterior ao início da série")
    start = validate_recurrence(payload.new_recurrence.rrule, payload.new_recurrence.dtstart,
                                payload.new_recurrence.timezone)
    if start < payload.effective_from:
        raise HTTPException(422, "dtstart da nova série não pode anteceder effective_from")
    old.recurrence_ends_at = payload.effective_from
    new_task = Task(
        title=old.title if payload.copy.get("title", True) else old.title,
        description=old.description if payload.copy.get("description", True) else None,
        status="todo", priority=old.priority if payload.copy.get("priority", True) else "medium",
        tags=list(old.tags) if payload.copy.get("tag_ids", True) else [],
        recurrence_rule=payload.new_recurrence.rrule, recurrence_dtstart=start,
        recurrence_timezone=payload.new_recurrence.timezone, supersedes_task_id=old.id)
    db.add(new_task)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"closed_task": serialize_task(get_task(db, old.id)), "new_task": serialize_task(get_task(db, new_task.id))}


@router.get("/calendar")
def get_calendar(from_: datetime = Query(alias="from"), to: datetime = Query(),
                 timezone_name: str = Query(default="UTC", alias="timezone"), db: Session = Depends(get_db)):
    if from_.tzinfo is None or to.tzinfo is None:
        raise HTTPException(422, "from e to devem incluir fuso horário")
    if from_ >= to:
        raise HTTPException(422, "from deve ser anterior a to")
    try:
        display_zone = ZoneInfo(timezone_name)
    except Exception as exc:
        raise HTTPException(422, "Fuso horário inválido") from exc
    tasks = db.scalars(select(Task).options(selectinload(Task.tags))).all()
    output = []
    for task in tasks:
        if task.recurrence_rule:
            start = task.recurrence_dtstart
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            # Expand slightly before the range so a recurrence that began earlier is still evaluated correctly.
            rule = rule_for(task)
            task_zone = ZoneInfo(task.recurrence_timezone)
            lower = from_.astimezone(task_zone)
            upper = to.astimezone(task_zone)
            candidates = rule.between(lower, upper, inc=True)
            keys = candidates
            overrides = {o.recurrence_key: o for o in db.scalars(select(TaskOccurrence).where(TaskOccurrence.task_id == task.id))}
            for key in keys:
                if task.recurrence_ends_at and key >= task.recurrence_ends_at:
                    continue
                override = overrides.get(key)
                if override and override.is_cancelled:
                    continue
                scheduled = override.due_at_override if override and override.due_at_override else key
                if not (from_ <= scheduled < to):
                    continue
                output.append({"id": str(override.id) if override else f"{task.id}:{key.isoformat()}",
                    "task_id": task.id, "kind": "recurring_occurrence",
                    "source": "materialized" if override else "virtual", "recurrence_key": key,
                    "title": (override.title_override if override and override.title_override else task.title),
                    "description": (override.description_override if override and override.description_override is not None else task.description),
                    "status": override.status_override if override and override.status_override else task.status,
                    "priority": override.priority_override if override and override.priority_override else task.priority,
                    "scheduled_at": scheduled, "due_at": scheduled if override and override.due_at_override else None,
                    "tag_ids": [tag.id for tag in task.tags]})
        elif task.due_at and from_ <= task.due_at < to:
            output.append({"id": str(task.id), "task_id": task.id, "kind": "single", "source": "task",
                "recurrence_key": None, "title": task.title, "description": task.description,
                "status": task.status, "priority": task.priority, "scheduled_at": task.due_at,
                "due_at": task.due_at, "tag_ids": [tag.id for tag in task.tags]})
    schedules = db.scalars(select(TaskSchedule).where(
        TaskSchedule.planned_date >= from_.astimezone(display_zone).date(),
        TaskSchedule.planned_date < to.astimezone(display_zone).date())).all()
    scheduled_task_ids = {item["task_id"] for item in output}
    task_map = {task.id: task for task in tasks}
    for schedule in schedules:
        task = task_map.get(schedule.task_id)
        if task is None:
            continue
        scheduled_at = datetime.combine(schedule.planned_date, datetime.min.time(), tzinfo=display_zone)
        output.append({"id": str(schedule.id), "task_id": task.id, "kind": "planned_work", "source": "schedule",
            "recurrence_key": None, "title": task.title, "description": schedule.notes or task.description,
            "status": task.status, "priority": task.priority, "scheduled_at": scheduled_at,
            "due_at": task.due_at, "planned_minutes": schedule.planned_minutes,
            "tag_ids": [tag.id for tag in task.tags]})
    output.sort(key=lambda item: item["scheduled_at"])
    return {"range": {"from": from_, "to": to, "timezone": timezone_name}, "items": output}


@router.patch("/tasks/{task_id}/occurrences/{recurrence_key}")
def update_occurrence(task_id: UUID, recurrence_key: datetime, payload: OccurrenceUpdate,
                      db: Session = Depends(get_db)):
    task = get_task(db, task_id)
    if not task.recurrence_rule:
        raise HTTPException(409, "A tarefa não é recorrente")
    key = recurrence_key
    if key.tzinfo is None:
        raise HTTPException(422, "recurrence_key deve incluir fuso horário")
    if task.recurrence_ends_at and key >= task.recurrence_ends_at:
        raise HTTPException(422, "Ocorrência está fora do período da série")
    candidate = key.astimezone(ZoneInfo(task.recurrence_timezone))
    rule = rule_for(task)
    match = rule.before(candidate, inc=True)
    if match is None or match != candidate:
        raise HTTPException(404, "A data não corresponde a uma ocorrência da regra")
    occurrence = db.scalar(select(TaskOccurrence).where(TaskOccurrence.task_id == task.id,
                                                        TaskOccurrence.recurrence_key == key))
    if occurrence is None:
        occurrence = TaskOccurrence(task_id=task.id, recurrence_key=key)
        db.add(occurrence)
    changes = payload.model_dump(exclude_unset=True)
    mapping = {"status": "status_override", "priority": "priority_override", "due_at": "due_at_override", "description": "description_override",
               "title": "title_override", "is_cancelled": "is_cancelled"}
    for field, value in changes.items():
        setattr(occurrence, mapping[field], value)
    if changes.get("status") == "done":
        occurrence.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": occurrence.id, "task_id": occurrence.task_id, "recurrence_key": occurrence.recurrence_key,
            "status": occurrence.status_override, "priority": occurrence.priority_override, "due_at": occurrence.due_at_override,
            "description": occurrence.description_override, "title": occurrence.title_override,
            "is_cancelled": occurrence.is_cancelled}


@router.post("/tags", status_code=201)
def create_tag(payload: TagCreate, db: Session = Depends(get_db)):
    tag = Tag(name=payload.name, color=payload.color)
    db.add(tag)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Já existe uma tag com esse nome") from exc
    db.refresh(tag)
    return {"id": tag.id, "name": tag.name, "color": tag.color}


@router.get("/tags")
def list_tags(db: Session = Depends(get_db)):
    return [{"id": t.id, "name": t.name, "color": t.color} for t in db.scalars(select(Tag).order_by(Tag.name))]


@router.post("/tasks/{task_id}/schedule", status_code=201)
def schedule_task(task_id: UUID, payload: ScheduleCreate, db: Session = Depends(get_db)):
    get_task(db, task_id)
    item = TaskSchedule(task_id=task_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "task_id": item.task_id, "planned_date": item.planned_date,
            "planned_minutes": item.planned_minutes, "notes": item.notes}
