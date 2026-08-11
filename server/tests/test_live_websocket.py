from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from starlette.websockets import WebSocketState

from app.authentication.security import hash_password
from app.database import Base, get_db
from app.main import create_app
from app.models import AdminUser, Project, ProjectOrigin
from app.websocket.client import ConnectionManager


class FakeSocket:
    application_state = WebSocketState.CONNECTED

    def __init__(self):
        self.messages = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def close(self, code=1000, reason=None):
        self.application_state = WebSocketState.DISCONNECTED

    async def send_json(self, message):
        self.messages.append(message)


@pytest.mark.asyncio
async def test_connection_manager_sends_live_action():
    manager = ConnectionManager()
    socket = FakeSocket()
    await manager.connect("session_live_123", socket)

    delivered = await manager.send_action("session_live_123", {"action_id": "action_1"})

    assert delivered is True
    assert manager.is_connected("session_live_123") is True
    assert socket.messages == [{"type": "diagnostic_action", "action": {"action_id": "action_1"}}]


@pytest.mark.asyncio
async def test_connection_manager_sends_chat_to_exact_client():
    manager = ConnectionManager()
    target_socket = FakeSocket()
    other_socket = FakeSocket()
    await manager.connect("session_target", target_socket)
    await manager.connect("session_other", other_socket)

    delivered = await manager.send_chat("session_target", {
        "message_id": "chat_1",
        "sender": "support",
        "message": "Hello client",
    })

    assert delivered is True
    assert target_socket.messages == [{
        "type": "chat_message",
        "message_id": "chat_1",
        "sender": "support",
        "message": "Hello client",
    }]
    assert other_socket.messages == []


@pytest.mark.asyncio
async def test_old_socket_disconnect_does_not_remove_replacement():
    manager = ConnectionManager()
    old_socket = FakeSocket()
    new_socket = FakeSocket()
    await manager.connect("session_replaced", old_socket)
    await manager.connect("session_replaced", new_socket)

    removed = manager.disconnect("session_replaced", old_socket)

    assert removed is False
    assert manager.clients["session_replaced"] is new_socket
    assert manager.is_connected("session_replaced") is True


@pytest.mark.asyncio
async def test_action_reports_not_live_without_websocket():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_local = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
      await conn.run_sync(Base.metadata.create_all)

    async def override_db():
        async with session_local() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_db

    async with session_local() as db:
        project = Project(public_id="PUBLIC_DEMO_PROJECT", name="Demo")
        db.add(project)
        await db.flush()
        db.add(ProjectOrigin(project_id=project.id, origin="http://127.0.0.1:5176"))
        db.add(AdminUser(email="admin@example.com", password_hash=hash_password("admin123")))
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
        register = await client.post("/api/client/register", json={
            "project_id": "PUBLIC_DEMO_PROJECT",
            "session_id": "session_live_test_12345",
            "visitor_id": "visitor_live_test_12345",
            "origin": "http://127.0.0.1:5176",
            "route": "/demo/",
            "referrer_origin": None,
            "consent_state": "GRANTED",
            "sdk_version": "0.2.0",
            "app_version": None,
            "diagnostics": {
                "browser": {"family": "Chrome", "version": "1", "os": "Win32"},
                "display": {"deviceCategory": "desktop"},
                "graphics": {},
                "network": {},
                "page": {"origin": "http://127.0.0.1:5176", "route": "/demo/"},
            },
        })
        assert register.status_code == 200
        action = await client.post("/api/actions", json={
            "session_id": "session_live_test_12345",
            "type": "SHOW_SUPPORT_BANNER",
            "parameters": {"message": "hello", "tone": "info", "duration_seconds": 3},
            "expires_at": (datetime.utcnow() + timedelta(minutes=1)).isoformat(),
        })
        assert action.status_code == 200
        assert action.json()["delivered_live"] is False
        pending = await client.get("/api/client/actions?session_id=session_live_test_12345&project_id=PUBLIC_DEMO_PROJECT")
        assert pending.status_code == 200
        assert pending.json()[0]["expires_at"].endswith("Z")


@pytest.mark.asyncio
async def test_dashboard_sessions_collapses_same_visitor_by_default():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_local = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
      await conn.run_sync(Base.metadata.create_all)

    async def override_db():
        async with session_local() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_db

    async with session_local() as db:
        project = Project(public_id="PUBLIC_DEMO_PROJECT", name="Demo")
        db.add(project)
        await db.flush()
        db.add(ProjectOrigin(project_id=project.id, origin="http://127.0.0.1:5176"))
        db.add(AdminUser(email="admin@example.com", password_hash=hash_password("admin123")))
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
        for suffix in ("first", "second"):
            response = await client.post("/api/client/register", json={
                "project_id": "PUBLIC_DEMO_PROJECT",
                "session_id": f"session_same_visitor_{suffix}_12345",
                "visitor_id": "visitor_same_person_12345",
                "origin": "http://127.0.0.1:5176",
                "route": f"/demo/{suffix}",
                "referrer_origin": None,
                "consent_state": "GRANTED",
                "sdk_version": "0.2.0",
                "app_version": None,
                "diagnostics": {
                    "browser": {"family": "Chrome", "version": "1", "os": "Win32"},
                    "display": {"deviceCategory": "desktop"},
                    "graphics": {},
                    "network": {},
                    "page": {"origin": "http://127.0.0.1:5176", "route": f"/demo/{suffix}"},
                },
            })
            assert response.status_code == 200

        collapsed = await client.get("/api/dashboard/sessions")
        stale = await client.get("/api/dashboard/sessions?include_stale=true")

        assert collapsed.status_code == 200
        assert stale.status_code == 200
        assert len(collapsed.json()) == 1
        assert len(stale.json()) == 2
