from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def get_schema_from_db(inspector) -> dict[str, str]:
    """Собирает краткое текстовое описание схемы БД по таблицам и внешним ключам.

    Args:
        inspector: SQLAlchemy async Inspector, созданный для нужного AsyncEngine.

    Returns:
        dict[str, str]: Словарь, где ключом является имя таблицы, а значением -
            строка с перечислением колонок и внешних ключей.
    """
    schema_parts = {}

    table_names = await inspector.get_table_names()
    for table_name in table_names:
        columns = [c["name"] for c in await inspector.get_columns(table_name)]
        foreign_keys = await inspector.get_foreign_keys(table_name)
        for fk in foreign_keys:
            for col in fk["constrained_columns"]:
                columns.append(f"{col} (foreign key to table '{fk['referred_table']}')")
        schema_parts[table_name] = ", ".join(columns)

    return schema_parts


async def build_prompt_values(engine: AsyncEngine) -> dict[str, str]:
    """Формирует справочные значения из БД для подстановки в системный промпт.

    Args:
        engine (AsyncEngine): SQLAlchemy AsyncEngine для подключения к БД.

    Returns:
        dict[str, str]: Словарь со строками contractors_str, exact_work_types_str,
            work_types_str, objects_str и cities_str.
    """
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT DISTINCT name FROM contractors ORDER BY name")
        )
        contractors = [row[0] for row in result.fetchall()]

        result = await conn.execute(
            text("SELECT DISTINCT work_type, unit FROM works ORDER BY work_type, unit")
        )
        work_type_unit_rows = result.fetchall()
        exact_work_types = sorted({row[0] for row in work_type_unit_rows})
        work_types_unit = [f"{row[0]} - {row[1]}" for row in work_type_unit_rows]

        result = await conn.execute(
            text("SELECT DISTINCT name FROM objects ORDER BY name")
        )
        objects = [row[0] for row in result.fetchall()]

        result = await conn.execute(
            text("SELECT DISTINCT city FROM objects ORDER BY city")
        )
        cities = [row[0] for row in result.fetchall()]

    return {
        "contractors_str": ", ".join(contractors),
        "exact_work_types_str": ", ".join(exact_work_types),
        "work_types_str": "\n".join(work_types_unit),
        "objects_str": ", ".join(objects),
        "cities_str": ", ".join(cities),
    }
