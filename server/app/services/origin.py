from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, ProjectOrigin


async def get_project_for_origin(db: AsyncSession, public_id: str, origin: str) -> Project | None:
    result = await db.execute(
        select(Project)
        .join(ProjectOrigin)
        .where(Project.public_id == public_id, ProjectOrigin.origin == origin)
    )
    return result.scalar_one_or_none()
