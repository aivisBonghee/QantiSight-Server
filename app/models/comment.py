from sqlalchemy import Column, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from app.database import Base


class Comment(Base):
    __tablename__ = "comments"

    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    author = Column(String(50), nullable=False, default="user")
    created_at = Column(DateTime, server_default=func.now())

    case = relationship("Case", back_populates="comments")
