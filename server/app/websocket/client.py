from datetime import datetime
from uuid import uuid4
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from starlette.websockets import WebSocketState

from app.database import SessionLocal
from app.models import BrowserSession, SessionEvent, SessionState

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.clients: dict[str, WebSocket] = {}
        self.connected_at: dict[str, datetime] = {}
        self.dashboards: set[WebSocket] = set()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        old_socket = self.clients.get(session_id)
        if old_socket and old_socket.application_state == WebSocketState.CONNECTED:
            await old_socket.close(code=4000, reason="Replaced by a newer client connection")
        self.clients[session_id] = websocket
        self.connected_at[session_id] = datetime.utcnow()

    def disconnect(self, session_id: str, websocket: WebSocket | None = None) -> bool:
        if websocket is not None and self.clients.get(session_id) is not websocket:
            return False
        self.clients.pop(session_id, None)
        self.connected_at.pop(session_id, None)
        return True

    def is_connected(self, session_id: str) -> bool:
        socket = self.clients.get(session_id)
        client_state = getattr(socket, "client_state", WebSocketState.CONNECTED)
        return bool(
            socket
            and socket.application_state == WebSocketState.CONNECTED
            and client_state == WebSocketState.CONNECTED
        )

    def snapshot(self) -> dict[str, dict]:
        return {
            session_id: {"connected_at": connected_at.isoformat()}
            for session_id, connected_at in self.connected_at.items()
            if self.is_connected(session_id)
        }

    async def send_action(self, session_id: str, action: dict) -> bool:
        socket = self.clients.get(session_id)
        if not self.is_connected(session_id):
            self.disconnect(session_id)
            return False
        try:
            await socket.send_json({"type": "diagnostic_action", "action": action})
            return True
        except RuntimeError:
            self.disconnect(session_id)
            return False

    async def send_chat(self, session_id: str, message: dict) -> bool:
        socket = self.clients.get(session_id)
        if not self.is_connected(session_id):
            self.disconnect(session_id)
            return False
        try:
            await socket.send_json({"type": "chat_message", **message})
            return True
        except RuntimeError:
            self.disconnect(session_id)
            return False

    async def broadcast_dashboard(self, message: dict) -> None:
        stale: list[WebSocket] = []
        for socket in tuple(self.dashboards):
            try:
                await socket.send_json(message)
            except RuntimeError:
                stale.append(socket)
        for socket in stale:
            self.dashboards.discard(socket)


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
            if message.get("type") == "client_ready":
                continue
            if message.get("type") == "action_ack":
                continue
            if message.get("type") == "chat_ack":
                continue
            if message.get("type") == "chat_message":
                chat_text = str(message.get("message", "")).strip()[:1000]
                if not chat_text:
                    continue
                message_id = str(message.get("message_id") or uuid4())[:80]
                async with SessionLocal() as db:
                    session = (
                        await db.execute(select(BrowserSession).where(BrowserSession.external_id == session_id))
                    ).scalar_one_or_none()
                    if not session:
                        continue
                    created_at = datetime.utcnow()
                    db.add(SessionEvent(
                        event_id=f"chat_{message_id}",
                        project_id=session.project_id,
                        session_id=session.id,
                        category="chat",
                        name="chat_message",
                        payload={
                            "message_id": message_id,
                            "sender": "client",
                            "message": chat_text,
                            "transport": "websocket",
                        },
                    ))
                    await db.commit()
                await manager.broadcast_dashboard({
                    "type": "chat_message",
                    "session_id": session_id,
                    "message_id": message_id,
                    "sender": "client",
                    "message": chat_text,
                    "created_at": created_at.isoformat(),
                })
    except WebSocketDisconnect:
        if manager.disconnect(session_id, websocket):
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


@router.websocket("/ws/dashboard")
async def dashboard_socket(websocket: WebSocket) -> None:
    if not websocket.scope.get("session", {}).get("admin_user_id"):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    manager.dashboards.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.dashboards.discard(websocket)
