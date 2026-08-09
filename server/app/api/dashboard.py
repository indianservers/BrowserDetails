from collections import Counter
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authentication.dependencies import current_admin
from app.database import get_db
from app.models import BrowserSession, BrowserVisitor, SessionEvent, SessionState
from app.schemas.dashboard import DashboardSummary, SessionSummary

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/dashboard/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request) -> HTMLResponse:
    if not request.session.get("admin_user_id"):
        return templates.TemplateResponse("login.html", {"request": request})
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/api/dashboard/summary", response_model=DashboardSummary)
async def summary(_admin=Depends(current_admin), db: AsyncSession = Depends(get_db)) -> DashboardSummary:
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    total_visitors = await db.scalar(select(func.count(BrowserVisitor.id)))
    sessions = (await db.execute(select(BrowserSession))).scalars().all()
    counts = Counter(s.state.value for s in sessions)
    browser_counts = Counter(s.browser_family for s in sessions if s.browser_family)
    errors_today = await db.scalar(
        select(func.count(SessionEvent.id)).where(
            SessionEvent.category == "application-error", SessionEvent.created_at >= today
        )
    )
    return DashboardSummary(
        total_visitors=total_visitors or 0,
        currently_connected=counts[SessionState.CONNECTED.value] + counts[SessionState.ACTIVE.value],
        active=counts[SessionState.ACTIVE.value],
        idle=counts[SessionState.IDLE.value],
        background=counts[SessionState.BACKGROUND.value],
        offline=counts[SessionState.OFFLINE.value],
        errors_today=errors_today or 0,
        most_common_browser=browser_counts.most_common(1)[0][0] if browser_counts else None,
    )


@router.get("/api/dashboard/sessions", response_model=list[SessionSummary])
async def sessions(q: str | None = None, state: str | None = None, _admin=Depends(current_admin), db: AsyncSession = Depends(get_db)) -> list[SessionSummary]:
    stmt = select(BrowserSession, BrowserVisitor).join(BrowserVisitor, BrowserVisitor.id == BrowserSession.visitor_id)
    if state:
        stmt = stmt.where(BrowserSession.state == SessionState(state))
    stmt = stmt.order_by(BrowserSession.last_seen_at.desc()).limit(500)
    rows = (await db.execute(stmt)).all()
    out: list[SessionSummary] = []
    for session, visitor in rows:
        text = f"{session.external_id} {visitor.external_id} {session.browser_family} {session.operating_system} {session.current_route}".lower()
        if q and q.lower() not in text:
            continue
        out.append(SessionSummary(
            session_id=session.external_id,
            visitor_id=visitor.external_id,
            state=session.state.value,
            consent_state=session.consent_state.value,
            browser=session.browser_family,
            os=session.operating_system,
            device=session.device_category,
            route=session.current_route,
            country=session.country,
            last_seen_at=session.last_seen_at,
        ))
    return out


@router.get("/api/dashboard/sessions/{session_id}/events")
async def session_events(session_id: str, _admin=Depends(current_admin), db: AsyncSession = Depends(get_db)) -> list[dict]:
    session = (
        await db.execute(select(BrowserSession).where(BrowserSession.external_id == session_id))
    ).scalar_one_or_none()
    if not session:
        return []
    events = (
        await db.execute(
            select(SessionEvent)
            .where(SessionEvent.session_id == session.id, SessionEvent.created_at >= datetime.utcnow() - timedelta(days=30))
            .order_by(SessionEvent.created_at.desc())
            .limit(300)
        )
    ).scalars().all()
    return [
        {
            "event_id": event.event_id,
            "category": event.category,
            "name": event.name,
            "payload": event.payload,
            "created_at": event.created_at.isoformat(),
        }
        for event in events
    ]
from app.authentication.dependencies import current_admin
