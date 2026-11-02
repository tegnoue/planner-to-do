from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.api.routes import router
from app.core.database import Base, engine
import app.models  # noqa: F401

app = FastAPI(title="Task Planner API", version="0.1.0")
app.include_router(router)
Base.metadata.create_all(bind=engine)
with engine.begin() as connection:
    if "priority_override" not in {column["name"] for column in inspect(engine).get_columns("task_occurrences")}:
        connection.execute(text("ALTER TABLE task_occurrences ADD COLUMN priority_override VARCHAR(20)"))
    if "remaining_seconds" not in {column["name"] for column in inspect(engine).get_columns("task_schedules")}:
        connection.execute(text("ALTER TABLE task_schedules ADD COLUMN remaining_seconds INTEGER"))

static_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(static_dir / "index.html")
