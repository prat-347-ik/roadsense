import asyncio
import logging
from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.session import get_session_factory
from app.models.entities import Reviewer

logger = logging.getLogger(__name__)


async def seed_default_reviewer():
    session_factory = get_session_factory()
    async with session_factory() as db:
        stmt = select(Reviewer).where(Reviewer.email == "admin@roadsense.local")
        res = await db.execute(stmt)
        if not res.scalar_one_or_none():
            admin = Reviewer(
                email="admin@roadsense.local",
                password_hash=get_password_hash("roadsense-admin-password"),
                role="admin",
            )
            db.add(admin)
            await db.commit()
            print("Default admin reviewer created: admin@roadsense.local")


if __name__ == "__main__":
    asyncio.run(seed_default_reviewer())
