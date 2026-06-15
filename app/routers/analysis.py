import os
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.case import Case
from app.config import settings
from app.services.ai_analysis import start_analysis_background

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))


@router.post("/{case_id}/reanalyze")
def reanalyze_case(case_id: str, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not case.image_path:
        raise HTTPException(status_code=400, detail="No image available for analysis")

    filename = os.path.basename(case.image_path)
    local_path = os.path.join(UPLOAD_DIR, filename)

    case.status = "PROCESSING"
    db.commit()

    start_analysis_background(
        case_id=case.id,
        local_path=local_path,
        filename=filename,
        organ=case.organ,
        stain_type=case.stain_type,
    )

    return {"case_id": case.id, "status": "PROCESSING", "message": "Re-analysis started"}


@router.get("/{case_id}/progress")
def get_analysis_progress(case_id: str, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return {
        "progress": case.analysis_progress or 0,
        "step": case.analysis_step or "",
        "status": case.status,
    }


@router.get("/status")
def analysis_status():
    return {"ai_model_url": settings.ai_model_url}
