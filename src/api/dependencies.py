from functools import lru_cache
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def _get_default_database_url() -> str:
    """Находит SQLite-базу в папке data/db по шаблону construction*.db.

    Returns:
        str: URL подключения SQLAlchemy к найденной SQLite-базе.

    Raises:
        FileNotFoundError: Если в папке data/db не найден ни один файл базы.
    """
    db_dir = Path(__file__).resolve().parents[2] / "data" / "db"
    db_files = sorted(db_dir.glob("construction*.db"))

    if not db_files:
        raise FileNotFoundError(
            "В папке data/db не найден файл базы данных по шаблону 'construction*.db'"
        )

    return f"sqlite:///{db_files[0].resolve()}"


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Создаёт и кэширует подключение SQLAlchemy к основной базе данных.

    Returns:
        Engine: SQLAlchemy engine для работы с SQLite или URL из переменной окружения.
    """
    db_path = os.getenv("DATABASE_URL") or _get_default_database_url()
    return create_engine(db_path, connect_args={"check_same_thread": False})
