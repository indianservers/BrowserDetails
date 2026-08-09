from datetime import datetime
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authentication.dependencies import current_admin
from app.database import get_db
from app.models import AdminUser, AuditLog, DiagnosticAction, DiagnosticResult, ActionStatus, BrowserSession, Project
from app.schemas.actions import DiagnosticActionCreate, DiagnosticActionOut
from app.services.actions import ACTION_DESCRIPTIONS, validate_action_parameters
from app.websocket.client import manager

router = APIRouter(prefix="/api/actions", tags=["safe diagnostics"])


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
    if payload.expires_at <= datetime.utcnow():
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
        expires_at=payload.expires_at,
    )
    db.add(action)
    await db.flush()
    delivered = await manager.send_action(session.external_id, {
        "action_id": action.action_id,
        "type": action.action_type,
        "parameters": action.parameters,
        "user_visible_description": action.user_visible_description,
        "expires_at": action.expires_at.isoformat(),
    })
    if delivered:
        action.status = ActionStatus.SENT
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
    await db.commit()
    return {"ok": True}
