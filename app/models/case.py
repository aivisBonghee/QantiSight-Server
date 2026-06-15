from sqlalchemy import Column, String, Integer, DateTime, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class Case(Base):
    __tablename__ = "cases"

    id = Column(String, primary_key=True)
    slide_id = Column(String, unique=True, nullable=False, index=True)
    specimen_no = Column(String(100), index=True)
    hospital_code = Column(String(10), nullable=False)
    patient_id = Column(String(30), nullable=False)
    patient_name = Column(String(50), nullable=False)
    exam_no = Column(String(30), nullable=False)
    exam_date = Column(String(10), nullable=False)
    organ = Column(String(20), nullable=False)
    stain_type = Column(String(10), nullable=False)
    diagnosis = Column(String(100))
    status = Column(String(15), nullable=False, default="WAITING")
    server_location = Column(String(15))
    image_path = Column(String(500))
    thumbnail_path = Column(String(500))
    confirmed_at = Column(DateTime)
    suspected_disease = Column(String(200))
    requested_stains = Column(String(200))
    ihc_markers = Column(String(300))
    molecular_test = Column(String(200))
    clinical_info = Column(Text)
    analysis_progress = Column(Integer, default=0)
    analysis_step = Column(String(50))
    analysis_task_id = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    qc_result = relationship("QcResult", back_populates="case", uselist=False)
    comments = relationship("Comment", back_populates="case", order_by="Comment.created_at")
