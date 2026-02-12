from sqlalchemy import Integer, String, DateTime, JSON, Float, func
from sqlalchemy.orm import Mapped, mapped_column
from db.database import Base

class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    source_type: Mapped[str] = mapped_column(String(20), default="text")  # text/pdf
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    extracted_data: Mapped[dict] = mapped_column(JSON)
    risk_score: Mapped[int] = mapped_column(Integer)
    risk_level: Mapped[str] = mapped_column(String(20))
    risk_reasons: Mapped[list] = mapped_column(JSON)

    expected_roi_percent: Mapped[float] = mapped_column(Float)
    rough_cash_gap: Mapped[float | None] = mapped_column(Float, nullable=True)

    verdict: Mapped[str] = mapped_column(String(120))

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
