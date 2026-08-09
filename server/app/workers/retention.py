import asyncio
from datetime import datetime, timedelta
from sqlalchemy import delete, select

from app.database import SessionLocal
from app.models import BrowserSession, Project, SessionEvent, SessionState


async def run_once() -> None:
    async with SessionLocal() as db:
        projects = (await db.execute(select(Project))).scalars().all()
        for project in projects:
            cutoff = datetime.utcnow() - timedelta(days=project.retention_days)
            await db.execute(delete(SessionEvent).where(SessionEvent.project_id == project.id, SessionEvent.created_at < cutoff))
            expired = (
                await db.execute(select(BrowserSession).where(BrowserSession.project_id == project.id, BrowserSession.last_seen_at < cutoff))
            ).scalars().all()
            for session in expired:
                session.state = SessionState.EXPIRED
        await db.commit()


async def main() -> None:
    while True:
        await run_once()
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
