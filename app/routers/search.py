from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Case
from app.schemas import CaseResponse

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=list[CaseResponse])
def search_slides(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    like = f"%{q}%"
    results = (
        db.query(Case)
        .options(joinedload(Case.qc_result))
        .filter(
            Case.slide_id.ilike(like)
            | Case.specimen_no.ilike(like)
            | Case.patient_name.ilike(like)
            | Case.patient_id.ilike(like)
            | Case.exam_no.ilike(like)
            | Case.diagnosis.ilike(like)
            | Case.server_location.ilike(like)
        )
        .limit(limit)
        .all()
    )
    return results
