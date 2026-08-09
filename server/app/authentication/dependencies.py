from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AdminUser


async def current_admin(request: Request, db: AsyncSession = Depends(get_db)) -> AdminUser:
    admin_id = request.session.get("admin_user_id")
    if not admin_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    admin = await db.get(AdminUser, admin_id)
    if not admin or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return admin
