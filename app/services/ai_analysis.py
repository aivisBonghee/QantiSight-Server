import os
import uuid
import json
import logging
import threading
from queue import Queue

import httpx

from app.database import SessionLocal
from app.models.case import Case
from app.models.qc_result import QcResult
from app.config import settings

logger = logging.getLogger(__name__)

PREDICT_TIMEOUT = 3600.0

IHC_NUCLEAR = {"IHC-ER", "IHC-PR", "IHC-KI67"}
IHC_MEMBRANE = {"IHC-HER2"}
IHC_STAINS = IHC_NUCLEAR | IHC_MEMBRANE

_analysis_queue = Queue()
_worker_started = False
_worker_lock = threading.Lock()


def _analysis_worker():
    while True:
        args = _analysis_queue.get()
        try:
            _run_analysis_pipeline(*args)
        except Exception as e:
            logger.error(f"Analysis worker error: {e}")
        finally:
            _analysis_queue.task_done()


def _ensure_worker():
    global _worker_started
    with _worker_lock:
        if not _worker_started:
            t = threading.Thread(target=_analysis_worker, daemon=True)
            t.start()
            _worker_started = True


def start_analysis_background(case_id: str, local_path: str, filename: str, organ: str, stain_type: str):
    _ensure_worker()
    _analysis_queue.put((case_id, local_path, filename, organ, stain_type))


def _update_progress(db, case_id: str, progress: int, step: str):
    case = db.query(Case).filter(Case.id == case_id).first()
    if case:
        case.analysis_progress = progress
        case.analysis_step = step
        db.commit()


def _run_analysis_pipeline(case_id: str, local_path: str, filename: str, organ: str, stain_type: str):
    db = SessionLocal()
    try:
        _run_ai_analysis(db, case_id, filename, organ, stain_type)

        from app.services.sftp_storage import upload_to_data_server, is_data_server_configured
        if is_data_server_configured():
            _run_sftp_transfer(db, case_id, local_path, filename)
    except Exception as e:
        logger.error(f"Analysis pipeline failed for case {case_id}: {e}")
    finally:
        db.close()


def _stain_matches(case_stain: str, detected_stain: str) -> bool:
    if detected_stain == "uncertain":
        return False
    if detected_stain == "HE":
        return case_stain == "HE"
    if detected_stain == "IHC-nuclear":
        return case_stain in IHC_NUCLEAR
    if detected_stain == "IHC-membrane":
        return case_stain in IHC_MEMBRANE
    return detected_stain == case_stain


def _classify_lesion_volume(tumor_pct: float) -> str:
    if tumor_pct < 10:
        return "Low"
    if tumor_pct < 30:
        return "Moderate"
    return "High"


def _run_ai_analysis(db, case_id: str, filename: str, organ: str, stain_type: str):
    image_path = f"{settings.ai_model_upload_base}/{filename}"

    _update_progress(db, case_id, 5, "분석 요청 중")

    try:
        _update_progress(db, case_id, 10, "AI 분석 중")

        resp = httpx.post(
            f"{settings.ai_model_url}/analyze",
            json={"path": image_path, "detail": True},
            timeout=PREDICT_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        _update_progress(db, case_id, 80, "결과 저장 중")

        detected_organ = data.get("organ", "uncertain")
        detected_stain = data.get("stain", "uncertain")
        ihc_subtype = data.get("ihc_subtype")
        tumor_pct = data.get("tumor_area_pct", 0.0)
        lesion_detail = data.get("lesion")

        organ_match = (
            detected_organ != "uncertain"
            and detected_organ.lower() == organ.lower()
        )
        organ_confidence = 0.0 if detected_organ == "uncertain" else 1.0

        stain_classification = detected_stain
        if detected_stain == "IHC" and ihc_subtype:
            stain_classification = f"IHC-{ihc_subtype}"
        stain_confidence = 0.0 if detected_stain == "uncertain" else 1.0

        lesion_volume = _classify_lesion_volume(tumor_pct) if tumor_pct else None

        ic_status = data.get("internal_control", "n/a")
        ic_pieces_raw = data.get("control_pieces", [])
        ic_present = True if ic_status == "present" else (False if ic_status == "absent" else None)
        ic_confidence = max((p.get("p", 0) for p in ic_pieces_raw), default=None) if ic_pieces_raw else None

        ic_pieces = []
        if ic_pieces_raw:
            try:
                import openslide
                slide_path = os.path.join(
                    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads")),
                    filename,
                )
                with openslide.OpenSlide(slide_path) as s:
                    sw, sh = s.dimensions
                for p in ic_pieces_raw:
                    x0, y0, x1, y1 = p["bbox"]
                    ic_pieces.append({
                        "bbox_pct": [round(x0 / sw, 4), round(y0 / sh, 4),
                                     round(x1 / sw, 4), round(y1 / sh, 4)],
                        "p": p["p"],
                    })
            except Exception as e:
                logger.warning(f"Control piece normalization failed: {e}")
                ic_pieces = ic_pieces_raw

        tissue_coverage = None
        if lesion_detail and lesion_detail.get("tissue_area_mm2"):
            tissue_coverage = min(lesion_detail["tissue_area_mm2"] / 10.0, 100.0)

        _update_progress(db, case_id, 85, "히트맵 생성 중")

        heatmap_filename = None
        try:
            from app.services.heatmap import find_and_generate_heatmap
            import os
            uploads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))
            heatmap_filename = find_and_generate_heatmap(filename, case_id, uploads_dir)
        except Exception as e:
            logger.warning(f"Heatmap generation skipped for {case_id}: {e}")

        _save_qc_results(db, case_id, {
            "organ_match": organ_match,
            "detected_organ": detected_organ,
            "organ_confidence": organ_confidence,
            "stain_classification": stain_classification,
            "stain_confidence": stain_confidence,
            "lesion_area_ratio": round(tumor_pct / 100, 4) if tumor_pct else None,
            "lesion_volume": lesion_volume,
            "tissue_coverage": tissue_coverage,
            "lesion_detail": lesion_detail,
            "heatmap_path": f"/uploads/{heatmap_filename}" if heatmap_filename else None,
            "control_tissue_present": ic_present,
            "control_tissue_confidence": ic_confidence,
            "control_tissue_status": ic_status,
            "control_pieces": ic_pieces,
        })

    except httpx.ConnectError:
        logger.warning(f"AI model not available, skipping analysis for case {case_id}")
        _update_progress(db, case_id, 0, "")
        case = db.query(Case).filter(Case.id == case_id).first()
        if case:
            case.status = "WAITING"
        db.commit()

    except Exception as e:
        logger.error(f"AI analysis failed for case {case_id}: {e}")
        _update_progress(db, case_id, 0, str(e)[:50])
        case = db.query(Case).filter(Case.id == case_id).first()
        if case:
            case.status = "ERROR"
        db.commit()


def _save_qc_results(db, case_id: str, data: dict):
    existing = db.query(QcResult).filter(QcResult.case_id == case_id).first()
    if existing:
        db.delete(existing)
        db.flush()

    qc = QcResult(
        id=str(uuid.uuid4()),
        case_id=case_id,
        focus_score=data.get("focus_score"),
        stain_quality=data.get("stain_quality"),
        tissue_coverage=data.get("tissue_coverage"),
        overall_qc_score=data.get("overall_qc_score"),
        organ_match=data.get("organ_match"),
        detected_organ=data.get("detected_organ"),
        organ_confidence=data.get("organ_confidence"),
        stain_classification=data.get("stain_classification"),
        stain_confidence=data.get("stain_confidence"),
        lesion_area_ratio=data.get("lesion_area_ratio"),
        lesion_volume=data.get("lesion_volume"),
        lesion_detail=json.dumps(data["lesion_detail"]) if data.get("lesion_detail") else None,
        control_tissue_present=data.get("control_tissue_present"),
        control_tissue_confidence=data.get("control_tissue_confidence"),
        control_tissue_status=data.get("control_tissue_status"),
        control_pieces=json.dumps(data["control_pieces"]) if data.get("control_pieces") else None,
        blur_regions=json.dumps(data["blur_regions"]) if data.get("blur_regions") else None,
        artifact_regions=json.dumps(data["artifact_regions"]) if data.get("artifact_regions") else None,
        tissue_region=json.dumps(data["tissue_region"]) if data.get("tissue_region") else None,
        heatmap_path=data.get("heatmap_path"),
    )
    db.add(qc)

    case = db.query(Case).filter(Case.id == case_id).first()
    if case:
        case.status = "DONE"
        case.analysis_progress = 100
        case.analysis_step = "완료"
    db.commit()

    logger.info(f"AI analysis complete: case={case_id}, organ={data.get('detected_organ')}, stain={data.get('stain_classification')}")


def _run_sftp_transfer(db, case_id: str, local_path: str, original_name: str):
    import os
    from app.services.sftp_storage import upload_to_data_server

    try:
        remote_path = upload_to_data_server(local_path, original_name)
        case = db.query(Case).filter(Case.id == case_id).first()
        if case:
            case.image_path = remote_path
            db.commit()
        os.remove(local_path)
        logger.info(f"SFTP transfer complete: {original_name} -> {remote_path}")
    except Exception as e:
        logger.error(f"SFTP transfer failed for {original_name}: {e}")
