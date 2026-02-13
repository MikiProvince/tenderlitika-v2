from sqlalchemy import Integer, String, DateTime, JSON, Float, func
from sqlalchemy.orm import Mapped, mapped_column
from db.database import Base
from sqlalchemy import ForeignKey, Boolean
from sqlalchemy.orm import relationship


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
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    user = relationship("User")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))

    plan: Mapped[str] = mapped_column(String(20), default="free")  # free/pro/business
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    api_keys = relationship("ApiKey", back_populates="user")

class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="default")

    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)  # sha256 hex
    last4: Mapped[str] = mapped_column(String(4))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="api_keys")
