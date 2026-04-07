from sqlalchemy import text
from sqlalchemy.engine import Engine


def get_schema_from_db(inspector) -> dict[str, str]:
    """
    Собирает краткое текстовое описание схемы БД по таблицам и внешним ключам.

    Args:
        inspector: SQLAlchemy Inspector, созданный для нужного Engine.
    Returns:
        dict[str, str]: Ключ - имя таблицы, значение - строка с перечислением полей и связей.
    """
    schema_parts = {}

    for table_name in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns(table_name)]
        foreign_keys = inspector.get_foreign_keys(table_name)
        for fk in foreign_keys:
            for col in fk["constrained_columns"]:
                columns.append(
                    f"{col} (foreign key to table '{fk['referred_table']}')"
                )
        schema_parts[table_name] = ", ".join(columns)

    return schema_parts


def build_prompt_values(engine: Engine) -> dict[str, str]:
    """
    Возвращает dict со справочными строками для подстановки в SYSTEM_PROMPT.

    Args:
        engine: SQLAlchemy Engine для подключения к БД.
    Returns: dict[str, str]:
        Keys: contractors_str, exact_work_types_str, work_types_str, objects_str, cities_str
    """
    with engine.connect() as conn:
        result = conn.execute(text("SELECT DISTINCT name FROM contractors ORDER BY name"))
        contractors = [row[0] for row in result.fetchall()]

        result = conn.execute(
            text("SELECT DISTINCT work_type, unit FROM works ORDER BY work_type, unit")
        )
        work_type_unit_rows = result.fetchall()
        exact_work_types = sorted({row[0] for row in work_type_unit_rows})
        work_types_unit = [f"{row[0]} - {row[1]}" for row in work_type_unit_rows]

        result = conn.execute(text("SELECT DISTINCT name FROM objects ORDER BY name"))
        objects = [row[0] for row in result.fetchall()]

        result = conn.execute(text("SELECT DISTINCT city FROM objects ORDER BY city"))
        cities = [row[0] for row in result.fetchall()]

    return {
        "contractors_str": ", ".join(contractors),
        "exact_work_types_str": ", ".join(exact_work_types),
        "work_types_str": "\n".join(work_types_unit),
        "objects_str": ", ".join(objects),
        "cities_str": ", ".join(cities),
    }
