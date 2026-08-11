from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlparse

from app.config import get_settings
from app.models import Project, ProjectOrigin


def is_development_lan_origin(origin: str) -> bool:
    if get_settings().environment != "development":
        return False
    parsed = urlparse(origin)
    if parsed.scheme != "http" or not parsed.hostname or not parsed.port:
        return False
    host = parsed.hostname
    if host in {"localhost", "127.0.0.1"}:
        return True
    parts = host.split(".")
    if len(parts) != 4:
        return False
    try:
        first, second = [int(part) for part in parts[:2]]
    except ValueError:
        return False
    return first == 10 or (first == 172 and 16 <= second <= 31) or (first == 192 and second == 168)


async def get_project_for_origin(db: AsyncSession, public_id: str, origin: str) -> Project | None:
    result = await db.execute(
        select(Project)
        .join(ProjectOrigin)
        .where(Project.public_id == public_id, ProjectOrigin.origin == origin)
    )
    project = result.scalar_one_or_none()
    if project:
        return project
    if is_development_lan_origin(origin):
        fallback = await db.execute(select(Project).where(Project.public_id == public_id))
        return fallback.scalar_one_or_none()
    return None
