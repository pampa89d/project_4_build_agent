from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine


async def get_schema_from_db(engine: AsyncEngine) -> dict[str, str]:
    """Собирает краткое текстовое описание схемы БД по таблицам и внешним ключам.

    Args:
        engine (AsyncEngine): SQLAlchemy AsyncEngine для подключения к БД.

    Returns:
        dict[str, str]: Словарь, где ключом является имя таблицы, а значением -
            строка с перечислением колонок и внешних ключей.
    """
    schema_parts = {}

    async with engine.connect() as conn:
        tables_result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        )
        table_names = [row[0] for row in tables_result.fetchall()]

        for table_name in table_names:
            cols_result = await conn.execute(
                text(f"PRAGMA table_info('{table_name}')")
            )
            columns = [row[1] for row in cols_result.fetchall()]

            fks_result = await conn.execute(
                text(f"PRAGMA foreign_key_list('{table_name}')")
            )
            for fk_row in fks_result.fetchall():
                col_name = fk_row[3]
                ref_table = fk_row[2]
                columns.append(
                    f"{col_name} (foreign key to table '{ref_table}')"
                )

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
