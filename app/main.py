import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.database import engine, Base
from app.routers import cases_router, search_router, upload_router, analysis_router, chat_router

Base.metadata.create_all(bind=engine)

_AUTO_MIGRATE = {
    "cases": [
        ("analysis_progress", "INTEGER DEFAULT 0"),
        ("analysis_step", "VARCHAR(50)"),
        ("analysis_task_id", "VARCHAR(100)"),
        ("pathologist", "VARCHAR(50)"),
    ],
    "qc_results": [
        ("lesion_detail", "TEXT"),
    ],
}
try:
    inspector = inspect(engine)
    with engine.connect() as conn:
        for table, columns in _AUTO_MIGRATE.items():
            existing = {col["name"] for col in inspector.get_columns(table)}
            for col_name, col_type in columns:
                if col_name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
        conn.commit()
except Exception:
    pass

app = FastAPI(title="QantiSight API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cases_router)
app.include_router(search_router)
app.include_router(upload_router)
app.include_router(analysis_router)
app.include_router(chat_router)

upload_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")


@app.get("/api/health")
def health():
    return {"status": "ok"}
