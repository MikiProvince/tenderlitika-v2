from sqlalchemy import Integer, String, Float, DateTime, JSON, ForeignKey, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.database import Base


# =========================
# ANALYSIS
# =========================

class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    user = relationship("User")

    source_type: Mapped[str] = mapped_column(String(20), default="text")
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    extracted_data: Mapped[dict] = mapped_column(JSON)

    risk_score: Mapped[int] = mapped_column(Integer)
    risk_level: Mapped[str] = mapped_column(String(20))
    risk_reasons: Mapped[list] = mapped_column(JSON)

    expected_roi_percent: Mapped[float] = mapped_column(Float)
    rough_cash_gap: Mapped[float | None] = mapped_column(Float, nullable=True)

    verdict: Mapped[str] = mapped_column(String(120))

    # =========================
    # NEW SAFE COST DATA
    # =========================

    input_cost_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_margin_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    safe_cost_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# =========================
# USER
# =========================

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))

    plan: Mapped[str] = mapped_column(String(20), default="free")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    api_keys = relationship("ApiKey", back_populates="user")


# =========================
# API KEY
# =========================

class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="default")

    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    last4: Mapped[str] = mapped_column(String(4))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    revoked_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    user = relationship("User", back_populates="api_keys")
