import json
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func, and_, or_, case as sql_case
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Case, QcResult, Comment
from app.schemas import CaseResponse, CaseListResponse, CaseCreate, CaseUpdate, CaseConfirmRequest, CommentCreate, CommentResponse

router = APIRouter(prefix="/api/cases", tags=["cases"])

IHC_NUCLEAR = {"IHC-ER", "IHC-PR", "IHC-KI67"}
IHC_MEMBRANE = {"IHC-HER2"}
IHC_STAINS = IHC_NUCLEAR | IHC_MEMBRANE

STAIN_CATEGORY_MAP = {
    "IHC-membrane": ["IHC-HER2"],
    "IHC-nuclear": ["IHC-ER", "IHC-PR", "IHC-KI67"],
}

_stain_match_expr = or_(
    and_(QcResult.stain_classification == "HE", Case.stain_type == "HE"),
    and_(QcResult.stain_classification == "IHC-nuclear", Case.stain_type.in_(list(IHC_NUCLEAR))),
    and_(QcResult.stain_classification == "IHC-membrane", Case.stain_type.in_(list(IHC_MEMBRANE))),
)


def _stain_matches_py(case_stain: str, detected: str) -> bool:
    if not detected or detected == "uncertain":
        return False
    if detected == "HE":
        return case_stain == "HE"
    if detected == "IHC-nuclear":
        return case_stain in IHC_NUCLEAR
    if detected == "IHC-membrane":
        return case_stain in IHC_MEMBRANE
    return detected == case_stain


def _apply_filters(query, params: dict):
    if params.get("search"):
        like = f"%{params['search']}%"
        query = query.filter(
            Case.slide_id.ilike(like)
            | Case.patient_name.ilike(like)
            | Case.patient_id.ilike(like)
            | Case.exam_no.ilike(like)
            | Case.diagnosis.ilike(like)
        )
    if params.get("organ"):
        vals = [v.strip() for v in params["organ"].split(",")]
        query = query.filter(Case.organ.in_(vals)) if len(vals) > 1 else query.filter(Case.organ == vals[0])
    if params.get("stain_type"):
        vals = [v.strip() for v in params["stain_type"].split(",")]
        expanded = []
        for v in vals:
            expanded.extend(STAIN_CATEGORY_MAP.get(v, [v]))
        query = query.filter(Case.stain_type.in_(expanded))
    if params.get("status"):
        vals = [v.strip() for v in params["status"].split(",")]
        query = query.filter(Case.status.in_(vals)) if len(vals) > 1 else query.filter(Case.status == vals[0])
    if params.get("hospital_code"):
        query = query.filter(Case.hospital_code == params["hospital_code"])
    if params.get("server_location"):
        query = query.filter(Case.server_location == params["server_location"])
    if params.get("pathologist"):
        query = query.filter(Case.pathologist == params["pathologist"])

    needs_qc_join = (
        params.get("organ_match") is not None
        or params.get("stain_match") is not None
        or params.get("control_tissue") is not None
        or params.get("qc_grade") is not None
        or params.get("has_issue") is not None
    )
    if needs_qc_join:
        if params.get("has_issue"):
            query = query.outerjoin(QcResult)
            query = query.filter(or_(
                QcResult.id == None,
                QcResult.organ_match == False,
                ~_stain_match_expr,
                QcResult.overall_qc_score == None,
                QcResult.overall_qc_score <= 0,
            ))
        else:
            query = query.join(QcResult)
        if params.get("organ_match") is not None:
            query = query.filter(QcResult.organ_match == (params["organ_match"] == "match"))
        if params.get("stain_match") is not None:
            if params["stain_match"] == "match":
                query = query.filter(_stain_match_expr)
            else:
                query = query.filter(~_stain_match_expr)
        if params.get("control_tissue") is not None:
            if params["control_tissue"] == "present":
                query = query.filter(QcResult.control_tissue_status == "present")
            else:
                query = query.filter(or_(
                    QcResult.control_tissue_status == "absent",
                    QcResult.control_tissue_status == None,
                    QcResult.control_tissue_present == False,
                ))
        if params.get("qc_grade"):
            g = params["qc_grade"]
            if g == "good":
                query = query.filter(QcResult.overall_qc_score >= 80)
            elif g == "fair":
                query = query.filter(QcResult.overall_qc_score >= 60, QcResult.overall_qc_score < 80)
            elif g == "poor":
                query = query.filter(QcResult.overall_qc_score < 60)
    return query


@router.get("", response_model=CaseListResponse)
def list_cases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    organ: Optional[str] = None,
    stain_type: Optional[str] = None,
    status: Optional[str] = None,
    hospital_code: Optional[str] = None,
    server_location: Optional[str] = None,
    pathologist: Optional[str] = None,
    organ_match: Optional[str] = None,
    stain_match: Optional[str] = None,
    control_tissue: Optional[str] = None,
    qc_grade: Optional[str] = None,
    has_issue: Optional[str] = None,
    sort_by: Optional[str] = "created_at",
    sort_dir: Optional[str] = "desc",
    db: Session = Depends(get_db),
):
    params = {
        "search": search, "organ": organ, "stain_type": stain_type,
        "status": status, "hospital_code": hospital_code,
        "server_location": server_location, "pathologist": pathologist,
        "organ_match": organ_match,
        "stain_match": stain_match, "control_tissue": control_tissue, "qc_grade": qc_grade,
        "has_issue": has_issue,
    }
    query = db.query(Case).options(joinedload(Case.qc_result), joinedload(Case.comments))
    query = _apply_filters(query, params)

    total = query.count()

    sort_col = getattr(Case, sort_by, None) or getattr(QcResult, sort_by, Case.created_at)
    if sort_col in (QcResult.overall_qc_score,):
        query = query.outerjoin(QcResult)
    if sort_dir == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    offset = (page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()

    return CaseListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/summary")
def get_summary(
    search: Optional[str] = None,
    organ: Optional[str] = None,
    stain_type: Optional[str] = None,
    status: Optional[str] = None,
    hospital_code: Optional[str] = None,
    server_location: Optional[str] = None,
    pathologist: Optional[str] = None,
    organ_match: Optional[str] = None,
    stain_match: Optional[str] = None,
    control_tissue: Optional[str] = None,
    qc_grade: Optional[str] = None,
    has_issue: Optional[str] = None,
    db: Session = Depends(get_db),
):
    params = {
        "search": search, "organ": organ, "stain_type": stain_type,
        "status": status, "hospital_code": hospital_code,
        "server_location": server_location, "pathologist": pathologist,
        "organ_match": organ_match,
        "stain_match": stain_match, "control_tissue": control_tissue, "qc_grade": qc_grade,
        "has_issue": has_issue,
    }
    base = db.query(Case)
    base = _apply_filters(base, params)
    total = base.count()

    qc_already_joined = any(v is not None for v in [organ_match, stain_match, control_tissue, qc_grade, has_issue])
    done_base = _apply_filters(db.query(Case), params).filter(Case.status == "DONE")
    done = done_base if qc_already_joined else done_base.join(QcResult)
    done_count = done.count()

    organ_match_count = done.filter(QcResult.organ_match == True).count()
    stain_correct = 0
    if done_count > 0:
        rows = done.with_entities(Case.stain_type, QcResult.stain_classification).all()
        stain_correct = sum(1 for r in rows if _stain_matches_py(r[0], r[1]))

    lesion_stats = done.filter(QcResult.lesion_area_ratio.isnot(None)).with_entities(
        func.avg(QcResult.lesion_area_ratio),
        func.count(),
    ).first()
    avg_lesion = float(lesion_stats[0] or 0)
    lesion_count = lesion_stats[1]

    low = done.filter(QcResult.lesion_volume == "Low").count()
    moderate = done.filter(QcResult.lesion_volume == "Moderate").count()
    high = done.filter(QcResult.lesion_volume == "High").count()

    avg_qc = done.with_entities(func.avg(QcResult.overall_qc_score)).scalar() or 0
    focus_issue = done.filter(QcResult.focus_score < 60).count()

    ctrl_total = done.filter(QcResult.control_tissue_status.in_(["present", "absent"])).count()
    ctrl_present = done.filter(QcResult.control_tissue_status == "present").count()

    return {
        "totalCases": total,
        "organMatchRate": (organ_match_count / done_count * 100) if done_count else 0,
        "organMismatchCount": done_count - organ_match_count,
        "stainAccuracy": (stain_correct / done_count * 100) if done_count else 0,
        "avgLesionRatio": avg_lesion,
        "lesionDistribution": {"low": low, "moderate": moderate, "high": high},
        "avgQcScore": float(avg_qc),
        "focusIssueCount": focus_issue,
        "controlTissueRate": (ctrl_present / ctrl_total * 100) if ctrl_total else 0,
        "controlTissueMissingCount": ctrl_total - ctrl_present,
    }


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(case_id: str, db: Session = Depends(get_db)):
    case = (
        db.query(Case)
        .options(joinedload(Case.qc_result), joinedload(Case.comments))
        .filter(Case.id == case_id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.get("/{case_id}/comments", response_model=List[CommentResponse])
def list_comments(case_id: str, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return db.query(Comment).filter(Comment.case_id == case_id).order_by(Comment.created_at).all()


@router.post("/{case_id}/comments", response_model=CommentResponse, status_code=201)
def create_comment(case_id: str, body: CommentCreate, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    comment = Comment(
        id=str(uuid.uuid4()),
        case_id=case_id,
        content=body.content,
        author=body.author or "user",
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


@router.put("/{case_id}/comments/{comment_id}", response_model=CommentResponse)
def update_comment(case_id: str, comment_id: str, body: CommentCreate, db: Session = Depends(get_db)):
    comment = db.query(Comment).filter(Comment.id == comment_id, Comment.case_id == case_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    comment.content = body.content
    db.commit()
    db.refresh(comment)
    return comment


@router.delete("/{case_id}/comments/{comment_id}", status_code=204)
def delete_comment(case_id: str, comment_id: str, db: Session = Depends(get_db)):
    comment = db.query(Comment).filter(Comment.id == comment_id, Comment.case_id == case_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    db.delete(comment)
    db.commit()


@router.patch("/{case_id}", response_model=CaseResponse)
def update_case(case_id: str, body: CaseUpdate, db: Session = Depends(get_db)):
    case = (
        db.query(Case)
        .options(joinedload(Case.qc_result), joinedload(Case.comments))
        .filter(Case.id == case_id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(case, field, value)
    case.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(case)
    return case


@router.put("/{case_id}/confirm", response_model=CaseResponse)
def confirm_case(case_id: str, body: CaseConfirmRequest, db: Session = Depends(get_db)):
    case = (
        db.query(Case)
        .options(joinedload(Case.qc_result), joinedload(Case.comments))
        .filter(Case.id == case_id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.status != "DONE":
        raise HTTPException(status_code=400, detail="Only DONE cases can be confirmed")

    if body.region_results and case.qc_result:
        rr = body.region_results
        if rr.blur_regions:
            case.qc_result.blur_regions = json.dumps(rr.blur_regions.model_dump())
        if rr.artifact_regions:
            case.qc_result.artifact_regions = json.dumps(rr.artifact_regions.model_dump())
        if rr.tissue_region:
            case.qc_result.tissue_region = json.dumps(rr.tissue_region.model_dump())

    case.status = "CONFIRMED"
    case.confirmed_at = datetime.utcnow()
    db.commit()
    db.refresh(case)
    return case


@router.delete("", status_code=204)
def delete_cases(ids: List[str] = Query(...), db: Session = Depends(get_db)):
    db.query(QcResult).filter(QcResult.case_id.in_(ids)).delete(synchronize_session=False)
    db.query(Comment).filter(Comment.case_id.in_(ids)).delete(synchronize_session=False)
    deleted = db.query(Case).filter(Case.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    if deleted == 0:
        raise HTTPException(status_code=404, detail="No cases found")


@router.post("", response_model=CaseResponse, status_code=201)
def create_case(body: CaseCreate, db: Session = Depends(get_db)):
    case = Case(id=str(uuid.uuid4()), **body.model_dump(), status="WAITING")
    db.add(case)
    db.commit()
    db.refresh(case)
    return case
