import pytest


def pytest_addoption(parser):
    """Регистрирует пользовательский флаг запуска интеграционных тестов.

    Args:
        parser: Объект парсера аргументов pytest.

    Returns:
        None: Функция изменяет конфигурацию pytest на месте.
    """
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that require a real LLM API key",
    )


def pytest_configure(config):
    """Добавляет описание пользовательского маркера integration в pytest.

    Args:
        config: Объект конфигурации pytest.

    Returns:
        None: Функция изменяет конфигурацию pytest на месте.
    """
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration (requires real LLM, skipped by default)",
    )


def pytest_collection_modifyitems(config, items):
    """Пропускает интеграционные тесты, если не передан соответствующий флаг.

    Args:
        config: Объект конфигурации pytest.
        items: Список собранных тестовых элементов.

    Returns:
        None: Функция добавляет маркеры skip к тестам при необходимости.
    """
    if not config.getoption("--run-integration"):
        skip_integration = pytest.mark.skip(
            reason="Pass --run-integration to run LLM integration tests"
        )
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)
