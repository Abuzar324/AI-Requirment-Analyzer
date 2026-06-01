from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import List, Optional

class RequirementInput(BaseModel):
    text: str
    persist: bool = False  # If True, stores the analyzed requirements in the database

class RequirementOut(BaseModel):
    id: Optional[int] = None
    text: str
    category: str  # "FR" or "NFR"
    ambiguity_score: float  # 0.0 to 1.0
    completeness_pct: float  # 0.0 to 100.0
    issues: List[str]
    suggestions: Optional[str] = None
    priority: str  # "Must Have", "Should Have", "Could Have", "Won't Have"
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class ConflictDetail(BaseModel):
    requirement_a: str
    requirement_b: str
    conflict_description: str

class AnalysisResult(BaseModel):
    requirements: List[RequirementOut]
    total_count: int
    fr_count: int
    nfr_count: int
    average_ambiguity: float
    average_completeness: float
    overall_risk_score: float
    # Expose intermediate penalty values for transparency and calibration
    ambiguity_penalty: Optional[float] = None
    conflict_penalty: Optional[float] = None
    incompleteness_risk: Optional[float] = None
    contradiction_penalty: Optional[float] = None
    high_risk_boost_applied: Optional[bool] = None
    conflicts: List[ConflictDetail]


class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: float
    result: Optional[AnalysisResult] = None
    error: Optional[str] = None

