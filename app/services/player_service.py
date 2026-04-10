from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.player import Player
from app.name_resolution.normalizer import normalize_name


async def search_players(
    db: AsyncSession,
    q: str | None = None,
    active: bool = True,
) -> list[Player]:
    stmt = select(Player)
    if active:
        stmt = stmt.where(Player.active.is_(True))
    if q:
        norm = normalize_name(q)
        stmt = stmt.where(Player.name_normalized.contains(norm))
    stmt = stmt.order_by(Player.name)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_player(db: AsyncSession, player_id: int) -> Player | None:
    result = await db.execute(select(Player).where(Player.id == player_id))
    return result.scalar_one_or_none()
