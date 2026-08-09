from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.database import SessionLocal
from app.models import BrowserSession, SessionEvent, SessionState

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.clients: dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.clients[session_id] = websocket

    def disconnect(self, session_id: str) -> None:
        self.clients.pop(session_id, None)

    async def send_action(self, session_id: str, action: dict) -> bool:
        socket = self.clients.get(session_id)
        if not socket:
            return False
        await socket.send_json({"type": "diagnostic_action", "action": action})
        return True


manager = ConnectionManager()


@router.websocket("/ws/client/{session_id}")
async def client_socket(websocket: WebSocket, session_id: str) -> None:
    await manager.connect(session_id, websocket)
    async with SessionLocal() as db:
        session = (
            await db.execute(select(BrowserSession).where(BrowserSession.external_id == session_id))
        ).scalar_one_or_none()
        if session:
            session.state = SessionState.CONNECTED
            session.last_seen_at = datetime.utcnow()
            await db.commit()
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "pong":
                continue
    except WebSocketDisconnect:
        manager.disconnect(session_id)
        async with SessionLocal() as db:
            session = (
                await db.execute(select(BrowserSession).where(BrowserSession.external_id == session_id))
            ).scalar_one_or_none()
            if session:
                session.state = SessionState.DISCONNECTED
                session.disconnected_at = datetime.utcnow()
                db.add(SessionEvent(
                    event_id=f"evt_{session.external_id}_disconnect_{int(datetime.utcnow().timestamp() * 1000)}",
                    project_id=session.project_id,
                    session_id=session.id,
                    category="connection",
                    name="session_disconnected",
                    payload={},
                ))
                await db.commit()
