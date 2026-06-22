import json

from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from app.models import Case, QcResult

IHC_NUCLEAR = {"IHC-ER", "IHC-PR", "IHC-KI67"}
IHC_MEMBRANE = {"IHC-HER2"}
IHC_STAINS = IHC_NUCLEAR | IHC_MEMBRANE

STAIN_CATEGORY_MAP = {
    "IHC-membrane": ["IHC-HER2"],
    "IHC-nuclear": ["IHC-ER", "IHC-PR", "IHC-KI67"],
}

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
        "description": "조건에 맞는 케이스를 검색합니다. 결과에 total(전체 건수)과 returned(반환 건수)가 포함됩니다. 반드시 '총 N건 중 M건 표시'처럼 전체 건수를 사용자에게 알려주세요.",
        "parameters": {
            "type": "object",
            "properties": {
                "organ": {
                    "type": "string",
                    "description": "장기 필터 (Breast, Stomach, Bladder, Thyroid, Colon, Brain)",
                },
                "stain_type": {
                    "type": "string",
                    "description": "염색 필터 (HE, IHC-HER2, IHC-ER, IHC-PR, IHC-KI67)",
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
                "has_issue": {
                    "type": "boolean",
                    "description": "부적합 케이스만 필터링 (장기 불일치, 염색 불일치, QC점수 0 또는 미산출 중 하나라도 해당)",
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
    {
        "name": "search_datasets",
        "description": "보유 데이터셋 메타정보를 검색합니다. 장기, 제공기관, 바이오마커, 키워드로 검색합니다. 데이터 출처, 수량, 수령일, 저장 위치, HE paired 여부 등의 정보를 제공합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색 키워드 (장기명, 기관명, 바이오마커 등)"},
            },
        },
    },
]

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


def query_qc_summary(db: Session, **kwargs):
    total = db.query(Case).count()
    done = db.query(Case).filter(Case.status == "DONE").join(QcResult)
    done_count = done.count()

    organ_match_count = done.filter(QcResult.organ_match == True).count()

    stain_correct = 0
    stain_mismatch = 0
    if done_count > 0:
        rows = done.with_entities(Case.stain_type, QcResult.stain_classification).all()
        for r in rows:
            if not r[1] or r[1] == "uncertain":
                continue
            if _stain_matches_py(r[0], r[1]):
                stain_correct += 1
            else:
                stain_mismatch += 1

    stain_evaluated = stain_correct + stain_mismatch
    avg_qc = done.with_entities(func.avg(QcResult.overall_qc_score)).scalar() or 0

    low = done.filter(QcResult.lesion_volume == "Low").count()
    moderate = done.filter(QcResult.lesion_volume == "Moderate").count()
    high = done.filter(QcResult.lesion_volume == "High").count()

    focus_issue = done.filter(QcResult.focus_score < 60).count()

    ctrl_total = done.filter(QcResult.control_tissue_present.isnot(None)).count()
    ctrl_present = done.filter(QcResult.control_tissue_present == True).count()

    issue_query = db.query(Case).outerjoin(QcResult).filter(or_(
        QcResult.id == None,
        QcResult.organ_match == False,
        ~_stain_match_expr,
        QcResult.overall_qc_score == None,
        QcResult.overall_qc_score <= 0,
    ))
    issue_count = issue_query.count()

    return {
        "totalCases": total,
        "doneCases": done_count,
        "organMatchRate": round(organ_match_count / done_count * 100, 1) if done_count else 0,
        "organMismatchCount": done_count - organ_match_count,
        "stainAccuracy": round(stain_correct / stain_evaluated * 100, 1) if stain_evaluated else 0,
        "stainMismatchCount": stain_mismatch,
        "avgQcScore": round(float(avg_qc), 1),
        "lesionDistribution": {"low": low, "moderate": moderate, "high": high},
        "focusIssueCount": focus_issue,
        "controlTissueRate": round(ctrl_present / ctrl_total * 100, 1) if ctrl_total else 0,
        "controlTissueMissingCount": ctrl_total - ctrl_present,
        "issueCount": issue_count,
    }


def search_cases(db: Session, **kwargs):
    query = db.query(Case).outerjoin(QcResult)

    if kwargs.get("organ"):
        query = query.filter(Case.organ == kwargs["organ"])
    if kwargs.get("stain_type"):
        expanded = STAIN_CATEGORY_MAP.get(kwargs["stain_type"], [kwargs["stain_type"]])
        query = query.filter(Case.stain_type.in_(expanded))
    if kwargs.get("status"):
        query = query.filter(Case.status == kwargs["status"])
    if kwargs.get("organ_match"):
        query = query.filter(QcResult.organ_match == (kwargs["organ_match"] == "match"))
    if kwargs.get("stain_match"):
        if kwargs["stain_match"] == "match":
            query = query.filter(_stain_match_expr)
        else:
            query = query.filter(~_stain_match_expr)
    if kwargs.get("has_issue"):
        query = query.filter(or_(
            QcResult.id == None,
            QcResult.organ_match == False,
            ~_stain_match_expr,
            QcResult.overall_qc_score == None,
            QcResult.overall_qc_score <= 0,
        ))

    total_count = query.count()
    limit = int(kwargs.get("limit", 20))
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

    return {"total": total_count, "returned": len(results), "cases": results}


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
            "control_tissue_status": qr.control_tissue_status,
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


def search_datasets(db: Session, **kwargs):
    import os
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "server_map.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"error": "데이터셋 정보 파일을 찾을 수 없습니다."}

    datasets = data.get("datasets", [])
    query = kwargs.get("query", "").lower()

    if not query:
        return {"total": len(datasets), "datasets": datasets}

    keywords = query.split()
    results = []
    for ds in datasets:
        searchable = " ".join([
            ds.get("organ", ""),
            ds.get("provider", ""),
            ds.get("note", ""),
            ds.get("location", ""),
            " ".join(ds.get("biomarkers", [])),
            " ".join(ds.get("tags", [])),
        ]).lower()
        if all(kw in searchable for kw in keywords):
            results.append(ds)

    return {"total": len(results), "datasets": results}


TOOL_FUNCTIONS = {
    "query_qc_summary": query_qc_summary,
    "search_cases": search_cases,
    "get_case_detail": get_case_detail,
    "find_server_data": find_server_data,
    "search_datasets": search_datasets,
}


def execute_tool(name: str, args: dict, db: Session):
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}"}
    return fn(db, **args)
