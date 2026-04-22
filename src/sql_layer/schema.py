from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


VIEW_NAME = "v_construction_data"


async def get_schema_from_db(engine: AsyncEngine) -> dict[str, str]:
    """Возвращает описание схемы VIEW v_construction_data.

    Args:
        engine (AsyncEngine): SQLAlchemy AsyncEngine для подключения к БД.

    Returns:
        dict[str, str]: Словарь с ключом-именем view и значением-строкой колонок.
    """
    async with engine.connect() as conn:
        cols_result = await conn.execute(
            text(f"PRAGMA table_xinfo('{VIEW_NAME}')")
        )
        columns = [row[1] for row in cols_result.fetchall()]

    return {VIEW_NAME: ", ".join(columns)}


async def build_prompt_values(engine: AsyncEngine) -> dict[str, str]:
    """Формирует справочные значения из VIEW для подстановки в системный промпт.

    Args:
        engine (AsyncEngine): SQLAlchemy AsyncEngine для подключения к БД.

    Returns:
        dict[str, str]: Словарь со строками contractors_str, exact_work_types_str,
            work_types_str, objects_str и cities_str.
    """
    async with engine.connect() as conn:
        result = await conn.execute(
            text(f"SELECT DISTINCT contractor_name FROM {VIEW_NAME} WHERE contractor_name IS NOT NULL ORDER BY contractor_name")
        )
        contractors = [row[0] for row in result.fetchall()]

        result = await conn.execute(
            text(f"SELECT DISTINCT work_type, unit FROM {VIEW_NAME} WHERE work_type IS NOT NULL ORDER BY work_type, unit")
        )
        work_type_unit_rows = result.fetchall()
        exact_work_types = sorted({row[0] for row in work_type_unit_rows})
        work_types_unit = [f"{row[0]} - {row[1]}" for row in work_type_unit_rows]

        result = await conn.execute(
            text(f"SELECT DISTINCT city FROM {VIEW_NAME} WHERE city IS NOT NULL ORDER BY city")
        )
        city = [row[0] for row in result.fetchall()]

        result = await conn.execute(
            text(f"SELECT DISTINCT object_name FROM {VIEW_NAME} WHERE object_name IS NOT NULL ORDER BY object_name")
        )
        objects = [row[0] for row in result.fetchall()]

    return {
        "contractors_str": ", ".join(contractors),
        "exact_work_types_str": ", ".join(exact_work_types),
        "work_types_str": "\n".join(work_types_unit),
        "cities_str": ", ".join(city),
        "objects_str": ", ".join(objects),
    }
