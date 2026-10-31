from sqlalchemy import text

from app.db.session import engine


async def check_database() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def close_database() -> None:
    await engine.dispose()
