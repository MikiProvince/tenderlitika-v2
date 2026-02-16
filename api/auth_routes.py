from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.deps import get_db
from db.models import User, ApiKey
from services.auth import hash_password, verify_password, generate_api_key, hash_api_key, last4
from services.current_user import get_current_user

router = APIRouter()

@router.post("/signup")
def signup(email: str, password: str, db: Session = Depends(get_db)):
    email = email.strip().lower()
    
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email")
    
    # bcrypt limit: 72 bytes
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=400,
            detail="Password too long (max 72 bytes for bcrypt). Use a shorter password."
    )

    exists = db.query(User).filter(User.email == email).first()
    if exists:
        raise HTTPException(status_code=409, detail="Email already exists")
    
    
    u = User(email=email, password_hash=hash_password(password), plan="free", is_active=True)
    db.add(u)
    db.commit()
    db.refresh(u)

    return {"user_id": u.id, "email": u.email, "plan": u.plan}

@router.post("/api-keys")
def create_api_key(
    name: str = "default",
    email: str | None = None,
    password: str | None = None,
    db: Session = Depends(get_db),
):
    """
    MVP-вариант: создаём ключ по email+password (без полноценной сессии/токенов).
    Позже заменим на normal auth (JWT/сессии).
    """
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password required")

    user = db.query(User).filter(User.email == email.strip().lower(), User.is_active == True).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    plain = generate_api_key()
    kh = hash_api_key(plain)

    row = ApiKey(
        user_id=user.id,
        name=name,
        key_hash=kh,
        last4=last4(plain),
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # ВАЖНО: показываем ключ только один раз
    return {"api_key": plain, "key_id": row.id, "last4": row.last4}

@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"user_id": user.id, "email": user.email, "plan": user.plan}

@router.post("/api-keys/{key_id}/revoke")
def revoke_key(key_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Key not found")

    row.is_active = False
    db.commit()
    return {"revoked": True, "key_id": key_id}
