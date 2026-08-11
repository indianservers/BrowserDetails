from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authentication.dependencies import current_admin
from app.database import get_db
from app.models import AdminUser, BrowserSession, SessionEvent
from app.websocket.client import manager

router = APIRouter(prefix="/api/chat", tags=["support chat"])


class SupportChatMessage(BaseModel):
    session_id: str = Field(min_length=1, max_length=180)
    message: str = Field(min_length=1, max_length=1000)


@router.post("")
async def send_support_chat(
    payload: SupportChatMessage,
    _admin: AdminUser = Depends(current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = (
        await db.execute(select(BrowserSession).where(BrowserSession.external_id == payload.session_id))
    ).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Unknown session")
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    message_id = str(uuid4())
    created_at = datetime.utcnow()
    delivered = await manager.send_chat(session.external_id, {
        "message_id": message_id,
        "sender": "support",
        "message": message,
        "created_at": created_at.isoformat(),
    })
    db.add(SessionEvent(
        event_id=f"chat_{message_id}",
        project_id=session.project_id,
        session_id=session.id,
        category="chat",
        name="chat_message",
        payload={
            "message_id": message_id,
            "sender": "support",
            "message": message,
            "transport": "websocket",
            "delivered_live": delivered,
        },
    ))
    await db.commit()
    await manager.broadcast_dashboard({
        "type": "chat_message",
        "session_id": session.external_id,
        "message_id": message_id,
        "sender": "support",
        "message": message,
        "delivered_live": delivered,
        "created_at": created_at.isoformat(),
    })
    return {"message_id": message_id, "delivered_live": delivered, "created_at": created_at.isoformat()}
