import asyncio
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authentication.dependencies import current_admin
from app.database import get_db
from app.models import AdminUser, AuditLog, DiagnosticAction, DiagnosticResult, ActionStatus, BrowserSession, Project, SessionEvent
from app.schemas.actions import DiagnosticActionCreate, DiagnosticActionOut
from app.services.actions import ACTION_DESCRIPTIONS, validate_action_parameters
from app.websocket.client import manager

router = APIRouter(prefix="/api/actions", tags=["safe diagnostics"])


def comparable_utc(value: datetime) -> datetime:
    if value.tzinfo:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def utc_iso(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


@router.post("", response_model=DiagnosticActionOut)
async def create_action(
    payload: DiagnosticActionCreate,
    admin: AdminUser = Depends(current_admin),
    db: AsyncSession = Depends(get_db),
) -> DiagnosticActionOut:
    session = (
        await db.execute(select(BrowserSession).where(BrowserSession.external_id == payload.session_id))
    ).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Unknown session")
    expires_at = comparable_utc(payload.expires_at)
    if expires_at <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="Action expiry must be in the future")
    try:
        params = validate_action_parameters(payload.type, payload.parameters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    project = await db.get(Project, session.project_id)
    if payload.type in {"OPEN_APPROVED_SUPPORT_PAGE", "OPEN_APPROVED_SUPPORT_IFRAME"}:
        url = str(params.get("url", ""))
        approved = set(project.approved_support_urls if project else [])
        if url not in approved:
            raise HTTPException(status_code=400, detail="Support URL is not approved for this project")
    action = DiagnosticAction(
        action_id=str(uuid4()),
        project_id=session.project_id,
        session_id=session.id,
        requested_by_admin_id=admin.id,
        action_type=payload.type,
        parameters=params,
        user_visible_description=ACTION_DESCRIPTIONS[payload.type],
        expires_at=expires_at,
    )
    db.add(action)
    await db.flush()
    await db.commit()
    try:
        delivered = await asyncio.wait_for(
            manager.send_action(session.external_id, {
                "action_id": action.action_id,
                "type": action.action_type,
                "parameters": action.parameters,
                "user_visible_description": action.user_visible_description,
                "expires_at": utc_iso(action.expires_at),
            }),
            timeout=2.0,
        )
    except TimeoutError:
        delivered = False
    db.add(SessionEvent(
        event_id=f"evt_{session.external_id}_action_{action.action_id[:8]}",
        project_id=session.project_id,
        session_id=session.id,
        category="support",
        name="action_requested",
        payload={
            "action_type": action.action_type,
            "delivered_live": delivered,
            "sender": "server" if action.action_type == "CHAT_FROM_SUPPORT" else "support",
            "message": params.get("message") if action.action_type == "CHAT_FROM_SUPPORT" else None,
        },
    ))
    db.add(AuditLog(
        admin_user_id=admin.id,
        project_id=session.project_id,
        action="diagnostic_requested",
        target_type="browser_session",
        target_id=session.external_id,
        details={"action_type": action.action_type, "delivered": delivered},
    ))
    await db.commit()
    return DiagnosticActionOut(
        action_id=action.action_id,
        type=payload.type,
        parameters=params,
        user_visible_description=action.user_visible_description,
        expires_at=action.expires_at,
        delivered_live=delivered,
    )


@router.post("/{action_id}/result")
async def action_result(action_id: str, result: dict, db: AsyncSession = Depends(get_db)) -> dict:
    action = (
        await db.execute(select(DiagnosticAction).where(DiagnosticAction.action_id == action_id))
    ).scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Unknown action")
    action.status = ActionStatus.COMPLETED
    db.add(DiagnosticResult(action_id=action.id, status="COMPLETED", result=result))
    db.add(SessionEvent(
        event_id=f"evt_{action.session_id}_result_{action.action_id[:8]}_{int(datetime.utcnow().timestamp() * 1000)}",
        project_id=action.project_id,
        session_id=action.session_id,
        category="support",
        name="action_result",
        payload={"action_type": action.action_type, "result": result},
    ))
    await db.commit()
    return {"ok": True}
