from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import ActionStatus, BrowserSession, BrowserVisitor, ConsentState, DiagnosticAction, Project, SessionCapabilities, SessionEvent, SessionState
from app.schemas.client import ClientEventRequest, HeartbeatRequest, RegisterClientRequest, RegisterClientResponse
from app.services.origin import get_project_for_origin
from app.services.privacy import anonymize_ip, hash_ip, redact_sensitive_payload

router = APIRouter(prefix="/api/client", tags=["client"])


def observed_ip(request: Request) -> str | None:
    if request.client:
        return request.client.host
    return None


@router.post("/register", response_model=RegisterClientResponse)
async def register_client(
    payload: RegisterClientRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> RegisterClientResponse:
    project = await get_project_for_origin(db, payload.project_id, payload.origin)
    if not project:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origin is not allowed for project")
    if payload.consent_state in {"DENIED", "WITHDRAWN"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Consent is required")

    visitor = (
        await db.execute(select(BrowserVisitor).where(BrowserVisitor.external_id == payload.visitor_id))
    ).scalar_one_or_none()
    now = datetime.utcnow()
    if not visitor:
        visitor = BrowserVisitor(external_id=payload.visitor_id, project_id=project.id)
        db.add(visitor)
        await db.flush()
    visitor.last_seen_at = now

    session = (
        await db.execute(select(BrowserSession).where(BrowserSession.external_id == payload.session_id))
    ).scalar_one_or_none()
    ip = observed_ip(request)
    browser = payload.diagnostics.browser
    if not session:
        session = BrowserSession(
            external_id=payload.session_id,
            project_id=project.id,
            visitor_id=visitor.id,
            consent_state=ConsentState(payload.consent_state),
            public_ip_hash=hash_ip(ip),
            public_ip_anonymized=anonymize_ip(ip),
            browser_family=browser.get("family"),
            browser_version=browser.get("version"),
            operating_system=browser.get("os"),
            device_category=payload.diagnostics.display.get("deviceCategory"),
            current_origin=payload.origin,
            current_route=payload.route,
            referrer_origin=payload.referrer_origin,
            sdk_version=payload.sdk_version,
            app_version=payload.app_version,
            state=SessionState.CONNECTED,
        )
        db.add(session)
        await db.flush()
    else:
        session.last_seen_at = now
        session.state = SessionState.CONNECTED
        session.consent_state = ConsentState(payload.consent_state)
        session.current_route = payload.route

    caps = (
        await db.execute(select(SessionCapabilities).where(SessionCapabilities.session_id == session.id))
    ).scalar_one_or_none()
    if not caps:
        caps = SessionCapabilities(session_id=session.id)
        db.add(caps)
    caps.browser = payload.diagnostics.browser
    caps.display = payload.diagnostics.display
    caps.graphics = payload.diagnostics.graphics
    caps.network = payload.diagnostics.network
    caps.page = payload.diagnostics.page
    caps.updated_at = now

    db.add(SessionEvent(
        event_id=f"evt_{payload.session_id}_{int(now.timestamp() * 1000)}",
        project_id=project.id,
        session_id=session.id,
        category="connection",
        name="connected",
        payload={"origin": payload.origin, "route": payload.route},
    ))
    await db.commit()
    base = str(get_settings().public_base_url).rstrip("/")
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    return RegisterClientResponse(accepted=True, websocket_url=f"{ws_base}/ws/client/{payload.session_id}")


@router.post("/heartbeat")
async def heartbeat(payload: HeartbeatRequest, db: AsyncSession = Depends(get_db)) -> dict:
    session = (
        await db.execute(select(BrowserSession).where(BrowserSession.external_id == payload.session_id))
    ).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Unknown session")
    session.last_seen_at = datetime.utcnow()
    session.state = SessionState(payload.state)
    if payload.route:
        session.current_route = payload.route.split("?", 1)[0]
    await db.commit()
    return {"ok": True}


@router.get("/actions")
async def pending_actions(session_id: str, project_id: str, db: AsyncSession = Depends(get_db)) -> list[dict]:
    session = (
        await db.execute(select(BrowserSession).where(BrowserSession.external_id == session_id))
    ).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Unknown session")
    project = await db.get(Project, session.project_id)
    if not project or project.public_id != project_id:
        raise HTTPException(status_code=403, detail="Project mismatch")
    actions = (
        await db.execute(
            select(DiagnosticAction)
            .where(
                DiagnosticAction.session_id == session.id,
                DiagnosticAction.status == ActionStatus.PENDING,
                DiagnosticAction.expires_at > datetime.utcnow(),
            )
            .order_by(DiagnosticAction.created_at.asc())
            .limit(10)
        )
    ).scalars().all()
    response = []
    for action in actions:
        action.status = ActionStatus.SENT
        response.append({
            "action_id": action.action_id,
            "type": action.action_type,
            "parameters": action.parameters,
            "user_visible_description": action.user_visible_description,
            "expires_at": action.expires_at.isoformat(),
        })
    await db.commit()
    return response


@router.post("/events")
async def custom_event(payload: ClientEventRequest, db: AsyncSession = Depends(get_db)) -> dict:
    session = (
        await db.execute(select(BrowserSession).where(BrowserSession.external_id == payload.session_id))
    ).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Unknown session")
    project = await db.get(Project, session.project_id)
    if project and project.permitted_events and payload.name not in project.permitted_events:
        raise HTTPException(status_code=400, detail="Event name is not approved for this project")
    clean_payload = redact_sensitive_payload(payload.payload)
    db.add(SessionEvent(
        event_id=payload.event_id,
        project_id=session.project_id,
        session_id=session.id,
        category="custom",
        name=payload.name,
        payload=clean_payload,
    ))
    await db.commit()
    return {"ok": True}
