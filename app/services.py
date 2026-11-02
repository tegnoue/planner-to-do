from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rrulestr
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Tag, Task


def validate_recurrence(rule: str, dtstart: datetime, timezone_name: str):
    try:
        zone = ZoneInfo(timezone_name)
        start = dtstart.astimezone(zone) if dtstart.tzinfo else dtstart.replace(tzinfo=zone)
        parsed = rrulestr(rule.removeprefix("RRULE:"), dtstart=start)
        parsed.after(start, inc=True)
    except (ValueError, TypeError, ZoneInfoNotFoundError) as exc:
        raise HTTPException(422, f"Regra RRULE ou fuso inválido: {exc}") from exc
    return start


def rule_for(task: Task):
    zone = ZoneInfo(task.recurrence_timezone or "UTC")
    start = task.recurrence_dtstart
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    start = start.astimezone(zone)
    return rrulestr(task.recurrence_rule.removeprefix("RRULE:"), dtstart=start)


def serialize_task(task: Task) -> dict:
    recurring = task.recurrence_rule is not None
    return {
        "id": task.id, "kind": "recurring" if recurring else "single", "title": task.title,
        "description": task.description, "status": task.status, "priority": task.priority,
        "due_at": task.due_at, "parent_task_id": task.parent_task_id,
        "tag_ids": [tag.id for tag in task.tags],
        "recurrence": ({"rrule": task.recurrence_rule, "dtstart": task.recurrence_dtstart,
                        "timezone": task.recurrence_timezone, "ends_at": task.recurrence_ends_at} if recurring else None),
        "supersedes_task_id": task.supersedes_task_id, "created_at": task.created_at,
    }


def resolve_tags(db: Session, tag_ids):
    tags = list(db.scalars(select(Tag).where(Tag.id.in_(tag_ids)))) if tag_ids else []
    if len(tags) != len(set(tag_ids)):
        raise HTTPException(422, "Um ou mais tag_ids não existem")
    return tags
