from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship

from app.database import Base

class Requirement(Base):
    __tablename__ = "requirements"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)
    category = Column(String, nullable=False)  # "FR" or "NFR"
    ambiguity_score = Column(Float, nullable=False)  # 0.0 to 1.0
    completeness_pct = Column(Float, nullable=False)  # 0.0 to 100.0
    issues = Column(JSON, nullable=False, default=list)  # JSON-encoded array of issue strings
    suggestions = Column(Text, nullable=True)  # AI suggestion rewrite
    priority = Column(String, nullable=False)  # "Must Have", "Should Have", "Could Have", "Won't Have"
    
    # Foreign Keys
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    owner = relationship("User", back_populates="requirements")
