from unittest.mock import MagicMock, patch

from src.sql_layer.prompts import (
    REVIEW_PROMPT,
    SYSTEM_PROMPT_TEMPLATE,
    build_messages,
    build_system_prompt,
)

FAKE_SCHEMAS = {"works": "id, work_type, unit", "objects": "id, name, city"}
FAKE_VALUES = {
    "contractors_str": "ООО Ромашка, ООО Василёк",
    "exact_work_types_str": "Кровельные работы, Отопление",
    "work_types_str": "Кровельные работы - м2\nОтопление - м.п.",
    "objects_str": "Офис 1, Офис 2",
    "cities_str": "Москва, Екатеринбург",
}


def test_review_prompt_not_empty():
    """Проверяет, что REVIEW_PROMPT задан и не является пустой строкой.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет значение через assert.
    """
    assert isinstance(REVIEW_PROMPT, str)
    assert len(REVIEW_PROMPT.strip()) > 0


def test_system_prompt_template_has_placeholders():
    """Проверяет наличие обязательных плейсхолдеров в шаблоне системного промпта.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет шаблон через assert.
    """
    for key in (
        "db_schemas",
        "contractors_str",
        "exact_work_types_str",
        "work_types_str",
        "objects_str",
        "cities_str",
    ):
        assert f"{{{key}}}" in SYSTEM_PROMPT_TEMPLATE, (
            f"Плейсхолдер {{{key}}} не найден в SYSTEM_PROMPT_TEMPLATE"
        )


def test_build_system_prompt_injects_all_values():
    """Проверяет подстановку схемы и справочных значений в системный промпт.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет содержимое результата через assert.
    """
    result = build_system_prompt(db_schemas=FAKE_SCHEMAS, **FAKE_VALUES)

    assert "works: id, work_type, unit" in result
    assert "objects: id, name, city" in result
    assert "ООО Ромашка" in result
    assert "Кровельные работы, Отопление" in result
    assert "Кровельные работы - м2" in result
    assert "Офис 1, Офис 2" in result
    assert "Москва, Екатеринбург" in result


def test_build_system_prompt_no_raw_placeholders():
    """Проверяет отсутствие необработанных плейсхолдеров после рендера промпта.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет результат через assert.
    """
    result = build_system_prompt(db_schemas=FAKE_SCHEMAS, **FAKE_VALUES)
    assert "{db_schemas}" not in result
    assert "{contractors_str}" not in result


def test_build_messages_roles():
    """Проверяет корректность ролей в списке сообщений для пайплайна.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет структуру результата через assert.
    """
    mock_engine = MagicMock()
    with (
        patch("src.sql_layer.prompts.sa_inspect", return_value=MagicMock()),
        patch("src.sql_layer.prompts.get_schema_from_db", return_value=FAKE_SCHEMAS),
        patch("src.sql_layer.prompts.build_prompt_values", return_value=FAKE_VALUES),
    ):
        messages = build_messages("Сколько объектов?", mock_engine)

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Сколько объектов?"


def test_build_messages_system_contains_schema():
    """Проверяет наличие схемы БД в системном сообщении.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет содержимое системного сообщения через assert.
    """
    mock_engine = MagicMock()
    with (
        patch("src.sql_layer.prompts.sa_inspect", return_value=MagicMock()),
        patch("src.sql_layer.prompts.get_schema_from_db", return_value=FAKE_SCHEMAS),
        patch("src.sql_layer.prompts.build_prompt_values", return_value=FAKE_VALUES),
    ):
        messages = build_messages("q", mock_engine)

    assert "works: id, work_type, unit" in messages[0]["content"]


def test_build_messages_does_not_mutate_question():
    """Проверяет, что сборка сообщений не изменяет исходный вопрос пользователя.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет содержимое пользовательского сообщения через assert.
    """
    question = "  Тест  "
    mock_engine = MagicMock()
    with (
        patch("src.sql_layer.prompts.sa_inspect", return_value=MagicMock()),
        patch("src.sql_layer.prompts.get_schema_from_db", return_value={}),
        patch("src.sql_layer.prompts.build_prompt_values", return_value=FAKE_VALUES),
    ):
        messages = build_messages(question, mock_engine)

    assert messages[1]["content"] == question
