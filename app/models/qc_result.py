from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from app.database import Base


class QcResult(Base):
    __tablename__ = "qc_results"

    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id"), unique=True, nullable=False)

    focus_score = Column(Float)
    stain_quality = Column(Float)
    tissue_coverage = Column(Float)
    overall_qc_score = Column(Float)

    organ_match = Column(Boolean)
    detected_organ = Column(String(20))
    organ_confidence = Column(Float)

    stain_classification = Column(String(20))
    stain_confidence = Column(Float)

    lesion_area_ratio = Column(Float)
    lesion_volume = Column(String(10))

    control_tissue_present = Column(Boolean)
    control_tissue_confidence = Column(Float)

    lesion_detail = Column(String)

    blur_regions = Column(String)
    artifact_regions = Column(String)
    tissue_region = Column(String)
    heatmap_path = Column(String)

    analyzed_at = Column(DateTime, server_default=func.now())

    case = relationship("Case", back_populates="qc_result")
