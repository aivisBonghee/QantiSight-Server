from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime


class RegionResult(BaseModel):
    score: Optional[float] = None
    coordinates: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None


class RegionResults(BaseModel):
    blur_regions: Optional[RegionResult] = None
    artifact_regions: Optional[RegionResult] = None
    tissue_region: Optional[RegionResult] = None


class CaseConfirmRequest(BaseModel):
    region_results: Optional[RegionResults] = None


class QcResultResponse(BaseModel):
    id: str
    focus_score: Optional[float]
    stain_quality: Optional[float]
    tissue_coverage: Optional[float]
    overall_qc_score: Optional[float]
    organ_match: Optional[bool]
    detected_organ: Optional[str]
    organ_confidence: Optional[float]
    stain_classification: Optional[str]
    stain_confidence: Optional[float]
    lesion_area_ratio: Optional[float]
    lesion_volume: Optional[str]
    lesion_detail: Optional[str] = None
    heatmap_path: Optional[str] = None
    control_tissue_present: Optional[bool]
    control_tissue_confidence: Optional[float]
    control_tissue_status: Optional[str] = None
    control_pieces: Optional[str] = None
    analyzed_at: Optional[datetime]

    class Config:
        from_attributes = True


class CommentResponse(BaseModel):
    id: str
    case_id: str
    content: str
    author: str
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class CommentCreate(BaseModel):
    content: str
    author: Optional[str] = "user"


class CaseResponse(BaseModel):
    id: str
    slide_id: str
    specimen_no: Optional[str]
    hospital_code: str
    patient_id: str
    patient_name: str
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None
    exam_no: str
    exam_date: str
    organ: str
    stain_type: str
    diagnosis: Optional[str]
    pathologist: Optional[str] = None
    status: str
    server_location: Optional[str]
    image_path: Optional[str]
    thumbnail_path: Optional[str]
    confirmed_at: Optional[datetime] = None
    suspected_disease: Optional[str] = None
    requested_stains: Optional[str] = None
    ihc_markers: Optional[str] = None
    molecular_test: Optional[str] = None
    clinical_info: Optional[str] = None
    analysis_progress: Optional[int] = 0
    analysis_step: Optional[str] = None
    created_at: Optional[datetime]
    qc_result: Optional[QcResultResponse]
    comments: List[CommentResponse] = []

    class Config:
        from_attributes = True


class CaseListResponse(BaseModel):
    items: List[CaseResponse]
    total: int
    page: int
    page_size: int


class CaseCreate(BaseModel):
    slide_id: str
    hospital_code: str
    patient_id: str
    patient_name: str
    exam_no: str
    exam_date: str
    organ: str
    stain_type: str
    diagnosis: Optional[str] = None
    server_location: Optional[str] = None


class CaseUpdate(BaseModel):
    specimen_no: Optional[str] = None
    hospital_code: Optional[str] = None
    patient_id: Optional[str] = None
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None
    exam_no: Optional[str] = None
    exam_date: Optional[str] = None
    organ: Optional[str] = None
    stain_type: Optional[str] = None
    diagnosis: Optional[str] = None
    pathologist: Optional[str] = None
    suspected_disease: Optional[str] = None
    clinical_info: Optional[str] = None
