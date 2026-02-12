from pydantic import BaseModel

class AnalysisReport(BaseModel):
    nmck: float | None
    risk_score: int
    risk_level: str
    expected_roi_percent: float
    verdict: str
