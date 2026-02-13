from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from db.deps import get_db
from db.models import ApiKey, User
from services.auth import hash_api_key

def get_current_user(
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> User:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key")

    key_h = hash_api_key(x_api_key)

    key_row = (
        db.query(ApiKey)
        .filter(ApiKey.key_hash == key_h, ApiKey.is_active == True)
        .first()
    )
    if not key_row:
        raise HTTPException(status_code=401, detail="Invalid API key")

    user = db.query(User).filter(User.id == key_row.user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User inactive or not found")

    return user
