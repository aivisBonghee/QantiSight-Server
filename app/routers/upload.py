import uuid
import os
import random
import string
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Case
from app.services.storage import save_image, generate_thumbnail
from app.services.ai_analysis import start_analysis_background

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/upload", tags=["upload"])

UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))
THUMB_DIR = os.path.join(UPLOAD_DIR, "thumbnails")


@router.post("")
async def upload_slide(
    file: UploadFile = File(...),
    case_id: Optional[str] = Form(None),
    slide_id: Optional[str] = Form(None),
    hospital_code: str = Form("SMC"),
    patient_id: str = Form(""),
    patient_name: str = Form(""),
    exam_no: str = Form(""),
    exam_date: str = Form(""),
    organ: str = Form(""),
    stain_type: str = Form("HE"),
    diagnosis: Optional[str] = Form(None),
    pathologist: str = Form(""),
    server_location: str = Form("server-1"),
    db: Session = Depends(get_db),
):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(THUMB_DIR, exist_ok=True)

    original_name = file.filename or "image.png"
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(original_name)[1]
    local_filename = f"{file_id}{ext}"

    local_path = await save_image(file, UPLOAD_DIR, local_filename)

    thumb_url = None
    thumb_name = f"thumb_{file_id}.png"
    result = generate_thumbnail(local_path, THUMB_DIR, thumb_name)
    if result:
        thumb_url = f"/uploads/thumbnails/{thumb_name}"

    now = datetime.now()
    rand = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    auto_slide_id = f"QS-{now.strftime('%Y%m%d-%H%M%S')}-{rand}"
    specimen = os.path.splitext(original_name)[0]

    image_url = f"/uploads/{local_filename}"

    if case_id:
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        case.image_path = image_url
        case.thumbnail_path = thumb_url
    else:
        case = Case(
            id=str(uuid.uuid4()),
            slide_id=auto_slide_id,
            specimen_no=specimen,
            hospital_code=hospital_code,
            patient_id=patient_id,
            patient_name=patient_name,
            exam_no=exam_no,
            exam_date=exam_date,
            organ=organ,
            stain_type=stain_type,
            diagnosis=diagnosis,
            pathologist=pathologist or None,
            status="PROCESSING",
            server_location=server_location,
            image_path=image_url,
            thumbnail_path=thumb_url,
        )
        db.add(case)

    db.commit()
    db.refresh(case)

    start_analysis_background(
        case_id=case.id,
        local_path=local_path,
        filename=local_filename,
        organ=organ,
        stain_type=stain_type,
    )

    return {
        "case_id": case.id,
        "slide_id": case.slide_id,
        "specimen_no": specimen,
        "image_path": case.image_path,
        "thumbnail_path": case.thumbnail_path,
        "original_name": original_name,
        "analysis": "started",
        "message": "Upload successful",
    }


@router.get("/status")
def upload_status():
    from app.services.sftp_storage import is_data_server_configured
    return {
        "data_server_configured": is_data_server_configured(),
        "local_upload_dir": UPLOAD_DIR,
    }
