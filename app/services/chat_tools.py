import json

from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from app.models import Case, QcResult

IHC_STAINS = {"HER2", "ER", "PR", "KI67"}

TOOL_DECLARATIONS = [
    {
        "name": "query_qc_summary",
        "description": "전체 QC 통계를 조회합니다. 총 케이스 수, 장기 일치율, 염색 정확도, 병변 분포, 평균 QC 점수, 컨트롤 티슈 비율 등을 반환합니다.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "search_cases",
        "description": "조건에 맞는 케이스를 검색합니다. 장기, 염색, 상태, 장기일치/염색일치 여부로 필터링할 수 있습니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "organ": {
                    "type": "string",
                    "description": "장기 필터 (Breast, Stomach, Bladder, Thyroid, Colon, Brain)",
                },
                "stain_type": {
                    "type": "string",
                    "description": "염색 필터 (HE, HER2, ER, PR, KI67)",
                },
                "status": {
                    "type": "string",
                    "description": "상태 필터 (DONE, PROCESSING, WAITING, ERROR)",
                },
                "organ_match": {
                    "type": "string",
                    "description": "장기 일치 필터 (match, mismatch)",
                },
                "stain_match": {
                    "type": "string",
                    "description": "염색 일치 필터 (match, mismatch)",
                },
                "limit": {
                    "type": "integer",
                    "description": "반환할 최대 케이스 수 (기본 10)",
                },
            },
        },
    },
    {
        "name": "get_case_detail",
        "description": "특정 케이스의 상세 정보와 QC 결과를 조회합니다. 케이스 ID 또는 검체번호로 검색합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string", "description": "케이스 ID"},
                "specimen_no": {"type": "string", "description": "검체번호"},
            },
        },
    },
    {
        "name": "find_server_data",
        "description": "서버에 저장된 병리 데이터의 위치를 검색합니다. 장기, 염색 종류, 키워드로 검색할 수 있습니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색 키워드"},
                "organ": {"type": "string", "description": "장기명"},
                "stain": {"type": "string", "description": "염색 종류"},
            },
        },
    },
]

_stain_match_expr = or_(
    and_(QcResult.stain_classification == "HE", Case.stain_type == "HE"),
    and_(
        QcResult.stain_classification.like("IHC%"),
        Case.stain_type.in_(list(IHC_STAINS)),
    ),
)


def _stain_matches_py(case_stain: str, detected: str) -> bool:
    if not detected or detected == "uncertain":
        return False
    if detected == "HE":
        return case_stain == "HE"
    if detected.startswith("IHC"):
        return case_stain in IHC_STAINS
    return detected == case_stain


def query_qc_summary(db: Session, **kwargs):
    total = db.query(Case).count()
    done = db.query(Case).filter(Case.status == "DONE").join(QcResult)
    done_count = done.count()

    organ_match_count = done.filter(QcResult.organ_match == True).count()

    stain_correct = 0
    if done_count > 0:
        rows = done.with_entities(Case.stain_type, QcResult.stain_classification).all()
        stain_correct = sum(1 for r in rows if _stain_matches_py(r[0], r[1]))

    avg_qc = done.with_entities(func.avg(QcResult.overall_qc_score)).scalar() or 0

    low = done.filter(QcResult.lesion_volume == "Low").count()
    moderate = done.filter(QcResult.lesion_volume == "Moderate").count()
    high = done.filter(QcResult.lesion_volume == "High").count()

    focus_issue = done.filter(QcResult.focus_score < 60).count()

    ctrl_total = done.filter(QcResult.control_tissue_present.isnot(None)).count()
    ctrl_present = done.filter(QcResult.control_tissue_present == True).count()

    return {
        "totalCases": total,
        "doneCases": done_count,
        "organMatchRate": round(organ_match_count / done_count * 100, 1) if done_count else 0,
        "organMismatchCount": done_count - organ_match_count,
        "stainAccuracy": round(stain_correct / done_count * 100, 1) if done_count else 0,
        "stainMismatchCount": done_count - stain_correct,
        "avgQcScore": round(float(avg_qc), 1),
        "lesionDistribution": {"low": low, "moderate": moderate, "high": high},
        "focusIssueCount": focus_issue,
        "controlTissueRate": round(ctrl_present / ctrl_total * 100, 1) if ctrl_total else 0,
        "controlTissueMissingCount": ctrl_total - ctrl_present,
    }


def search_cases(db: Session, **kwargs):
    query = db.query(Case).outerjoin(QcResult)

    if kwargs.get("organ"):
        query = query.filter(Case.organ == kwargs["organ"])
    if kwargs.get("stain_type"):
        query = query.filter(Case.stain_type == kwargs["stain_type"])
    if kwargs.get("status"):
        query = query.filter(Case.status == kwargs["status"])
    if kwargs.get("organ_match"):
        query = query.filter(QcResult.organ_match == (kwargs["organ_match"] == "match"))
    if kwargs.get("stain_match"):
        if kwargs["stain_match"] == "match":
            query = query.filter(_stain_match_expr)
        else:
            query = query.filter(~_stain_match_expr)

    limit = int(kwargs.get("limit", 10))
    cases = query.order_by(Case.created_at.desc()).limit(limit).all()

    results = []
    for c in cases:
        item = {
            "id": c.id,
            "specimen_no": c.specimen_no,
            "organ": c.organ,
            "stain_type": c.stain_type,
            "status": c.status,
            "patient_name": c.patient_name,
        }
        if c.qc_result:
            qr = c.qc_result
            item.update({
                "detected_organ": qr.detected_organ,
                "organ_match": qr.organ_match,
                "stain_classification": qr.stain_classification,
                "lesion_volume": qr.lesion_volume,
                "overall_qc_score": qr.overall_qc_score,
            })
        results.append(item)

    return {"count": len(results), "cases": results}


def get_case_detail(db: Session, **kwargs):
    case = None
    if kwargs.get("case_id"):
        case = db.query(Case).outerjoin(QcResult).filter(Case.id == kwargs["case_id"]).first()
    elif kwargs.get("specimen_no"):
        case = db.query(Case).outerjoin(QcResult).filter(Case.specimen_no == kwargs["specimen_no"]).first()

    if not case:
        return {"error": "케이스를 찾을 수 없습니다."}

    result = {
        "id": case.id,
        "specimen_no": case.specimen_no,
        "organ": case.organ,
        "stain_type": case.stain_type,
        "status": case.status,
        "patient_name": case.patient_name,
        "patient_id": case.patient_id,
        "diagnosis": case.diagnosis,
        "exam_date": str(case.exam_date) if case.exam_date else None,
    }
    if case.qc_result:
        qr = case.qc_result
        result["qc"] = {
            "detected_organ": qr.detected_organ,
            "organ_match": qr.organ_match,
            "organ_confidence": qr.organ_confidence,
            "stain_classification": qr.stain_classification,
            "lesion_volume": qr.lesion_volume,
            "lesion_area_ratio": qr.lesion_area_ratio,
            "overall_qc_score": qr.overall_qc_score,
            "focus_score": qr.focus_score,
            "tissue_coverage": qr.tissue_coverage,
            "control_tissue_present": qr.control_tissue_present,
        }
        if qr.lesion_detail:
            try:
                result["qc"]["lesion_detail"] = json.loads(qr.lesion_detail)
            except (json.JSONDecodeError, TypeError):
                pass

    return result


def find_server_data(db: Session, **kwargs):
    from app.services.server_index import search_servers

    return search_servers(
        query=kwargs.get("query", ""),
        organ=kwargs.get("organ"),
        stain=kwargs.get("stain"),
    )


TOOL_FUNCTIONS = {
    "query_qc_summary": query_qc_summary,
    "search_cases": search_cases,
    "get_case_detail": get_case_detail,
    "find_server_data": find_server_data,
}


def execute_tool(name: str, args: dict, db: Session):
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}"}
    return fn(db, **args)
