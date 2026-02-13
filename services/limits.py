from __future__ import annotations

from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session

from db.models import Analysis, User

PLAN_LIMITS = {
    "free": 30,       # 30 анализов / месяц
    "pro": 500,
    "business": 5000,
}

def month_start_utc(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, 1, tzinfo=timezone.utc)

def check_monthly_quota(db: Session, user: User) -> None:
    limit = PLAN_LIMITS.get(user.plan, 30)

    now = datetime.now(timezone.utc)
    start = month_start_utc(now)

    used = (
        db.query(Analysis)
        .filter(Analysis.user_id == user.id, Analysis.created_at >= start)
        .count()
    )

    if used >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Quota exceeded: {used}/{limit} analyses this month for plan={user.plan}",
        )
