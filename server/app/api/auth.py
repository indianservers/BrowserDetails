from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authentication.security import verify_password
from app.database import get_db
from app.models import AdminUser, AuditLog

router = APIRouter(prefix="/api/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/login")
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    admin = (
        await db.execute(select(AdminUser).where(AdminUser.email == payload.email, AdminUser.is_active.is_(True)))
    ).scalar_one_or_none()
    if not admin or not verify_password(payload.password, admin.password_hash):
        db.add(AuditLog(action="admin_login_failed", target_type="admin_user", target_id=payload.email, result="FAILED"))
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    request.session["admin_user_id"] = admin.id
    db.add(AuditLog(admin_user_id=admin.id, action="admin_login", target_type="admin_user", target_id=str(admin.id)))
    await db.commit()
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    admin_id = request.session.pop("admin_user_id", None)
    if admin_id:
        db.add(AuditLog(admin_user_id=admin_id, action="admin_logout", target_type="admin_user", target_id=str(admin_id)))
        await db.commit()
    return {"ok": True}
