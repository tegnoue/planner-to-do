from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.database import Base, engine
import app.models  # noqa: F401

app = FastAPI(title="Task Planner API", version="0.1.0")
app.include_router(router)
Base.metadata.create_all(bind=engine)

static_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(static_dir / "index.html")
