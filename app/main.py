import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import engine, Base
from app.routers import cases_router, search_router, upload_router

Base.metadata.create_all(bind=engine)

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

upload_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")


@app.get("/api/health")
def health():
    return {"status": "ok"}
