from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

db_dir = Path.cwd().parent / "data" / "db"
db_files = sorted(db_dir.glob("construction*.db"))

if not db_files:
    raise FileNotFoundError("Database file matching 'construction*.db' was not found")

db_path = db_files[0]

async_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")


async def query_to_sqllite(query: str):
    async with async_engine.connect() as conn:
        result = await conn.execute(text(query))

    data = []
    data.append(tuple(result.keys()))
    data.append(result.fetchall())
    return data
