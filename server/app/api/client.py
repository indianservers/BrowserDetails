from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import ActionStatus, BrowserSession, BrowserVisitor, ConsentState, DiagnosticAction, DiagnosticResult, Project, SessionCapabilities, SessionEvent, SessionState
from app.schemas.client import ClientEventRequest, ClientIdentityRequest, HeartbeatRequest, RegisterClientRequest, RegisterClientResponse
from app.services.origin import get_project_for_origin
from app.services.privacy import anonymize_ip, hash_ip, redact_sensitive_payload

router = APIRouter(prefix="/api/client", tags=["client"])


def observed_ip(request: Request) -> str | None:
    for header in ("cf-connecting-ip", "true-client-ip", "x-real-ip"):
        value = request.headers.get(header)
        if value:
            return value.strip()
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    forwarded = request.headers.get("forwarded")
    if forwarded:
        for part in forwarded.split(";"):
            key, _, value = part.strip().partition("=")
            if key.lower() == "for" and value:
                return value.strip('"[]')
    if request.client:
        return request.client.host
    return None


def display_ip(ip: str | None) -> str | None:
    settings = get_settings()
    if settings.environment == "development":
        return ip
    return anonymize_ip(ip) if settings.ip_anonymization else ip


def utc_iso(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


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
            public_ip_anonymized=display_ip(ip),
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
        session.public_ip_hash = hash_ip(ip)
        session.public_ip_anonymized = display_ip(ip)
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
    base = str(request.base_url).rstrip("/")
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


@router.post("/identity")
async def update_identity(payload: ClientIdentityRequest, db: AsyncSession = Depends(get_db)) -> dict:
    session = (
        await db.execute(select(BrowserSession).where(BrowserSession.external_id == payload.session_id))
    ).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Unknown session")
    project = await db.get(Project, session.project_id)
    if not project or project.public_id != payload.project_id:
        raise HTTPException(status_code=403, detail="Project mismatch")
    visitor = await db.get(BrowserVisitor, session.visitor_id)
    if not visitor:
        raise HTTPException(status_code=404, detail="Unknown visitor")
    visitor.pseudonymous_ref = payload.display_name
    session.last_seen_at = datetime.utcnow()
    db.add(SessionEvent(
        event_id=f"evt_{session.external_id}_identity_{int(datetime.utcnow().timestamp() * 1000)}",
        project_id=session.project_id,
        session_id=session.id,
        category="identity",
        name="display_name_saved",
        payload={"display_name": payload.display_name},
    ))
    await db.commit()
    return {"ok": True, "display_name": payload.display_name}


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
    now = datetime.utcnow()
    completed_action_ids = select(DiagnosticResult.action_id)
    resend_cutoff = now - timedelta(seconds=get_settings().action_resend_grace_seconds)
    actions = (
        await db.execute(
            select(DiagnosticAction)
            .where(
                DiagnosticAction.session_id == session.id,
                DiagnosticAction.status.in_([ActionStatus.PENDING, ActionStatus.SENT]),
                DiagnosticAction.id.not_in(completed_action_ids),
                DiagnosticAction.expires_at > now,
                (
                    (DiagnosticAction.status == ActionStatus.PENDING)
                    | (
                        (DiagnosticAction.status == ActionStatus.SENT)
                        & (DiagnosticAction.created_at <= resend_cutoff)
                    )
                ),
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
            "expires_at": utc_iso(action.expires_at),
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
    built_in_client_events = {
        "application_error",
        "browser_blurred",
        "browser_focused",
        "client_chat_message",
        "consent_granted",
        "consent_withdrawn",
        "network_offline",
        "network_online",
        "page_hidden",
        "page_visible",
        "reconnected",
        "sdk_error",
        "viewport_changed",
    }
    if project and project.permitted_events and payload.name not in project.permitted_events and payload.name not in built_in_client_events:
        raise HTTPException(status_code=400, detail="Event name is not approved for this project")
    clean_payload = redact_sensitive_payload(payload.payload)
    category = "chat" if payload.name == "client_chat_message" else "custom"
    db.add(SessionEvent(
        event_id=payload.event_id,
        project_id=session.project_id,
        session_id=session.id,
        category=category,
        name=payload.name,
        payload=clean_payload,
    ))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
    return {"ok": True}
