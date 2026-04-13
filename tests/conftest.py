from collections import defaultdict
from pathlib import Path

import pytest

LOGS_DIR = Path(__file__).resolve().parent / "logs"


def _get_test_log_path(nodeid: str) -> Path | None:
    """Возвращает путь к лог-файлу для тестового модуля из nodeid.

    Args:
        nodeid: Идентификатор теста в формате pytest.

    Returns:
        Path | None: Путь к лог-файлу или None, если тест не из папки tests.
    """
    file_part = nodeid.split("::", maxsplit=1)[0]
    if not file_part.startswith("tests/"):
        return None

    log_name = Path(file_part).stem + ".log"
    return LOGS_DIR / log_name


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
    LOGS_DIR.mkdir(exist_ok=True)
    config._test_file_logs = defaultdict(
        lambda: {"passed": 0, "failed": 0, "skipped": 0, "entries": []}
    )
    tests_dir = Path(__file__).resolve().parent
    for test_file in tests_dir.glob("test_*.py"):
        config._test_file_logs[LOGS_DIR / f"{test_file.stem}.log"]

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
    for item in items:
        log_path = _get_test_log_path(item.nodeid)
        if log_path is not None:
            config._test_file_logs[log_path]

    if not config.getoption("--run-integration"):
        skip_integration = pytest.mark.skip(
            reason="Pass --run-integration to run LLM integration tests"
        )
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)


def _format_error_summary(longrepr) -> str:
    """Извлекает из longrepr только тип ошибки и assert-сообщение.

    Отсекает исходный код функций, traceback фреймы
    и код библиотек, оставляя только суть ошибки.

    Args:
        longrepr: Объект longrepr из pytest report.

    Returns:
        str: Компактное описание ошибки.
    """
    repr_text = str(longrepr)

    # Ищем последнюю строку с AssertionError или исключением,
    # а также assert-выражение (строка, начинающаяся с 'assert')
    error_lines = []
    capture = False

    for line in repr_text.splitlines():
        stripped = line.strip()

        # Начинаем захват с assert-строки теста
        if stripped.startswith("assert "):
            capture = True
            error_lines = [stripped]
            continue

        # Строка с типом ошибки (E   ...)
        if stripped.startswith("E   "):
            capture = True
            error_lines.append(stripped)
            continue

        # Строка с '>', указывающая место в тесте
        if stripped.startswith(">   ") or stripped.endswith(":"):
            if capture:
                # Это строка файла — проверим, из tests/ ли она
                if stripped.startswith("tests/"):
                    error_lines.append(stripped)
            continue

        # Продолжаем захват, если уже собираем
        if capture and stripped and not stripped.startswith(
            ("_ _ _", ".venv", "self =")
        ):
            # Строки с параметрами теста (item =, engine =, ...)
            if any(
                stripped.startswith(p)
                for p in ("item =", "engine =", "request =")
            ):
                continue
            error_lines.append(stripped)

    if error_lines:
        return "\n".join(error_lines)

    # Fallback: берём последние 5 непустых строк
    lines = [l for l in repr_text.splitlines() if l.strip()]
    return "\n".join(lines[-5:]) if lines else repr_text[:500]


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Собирает результаты выполнения тестов для последующей записи в логи.

    Args:
        item: Объект тестового кейса pytest.
        call: Информация о фазе выполнения теста.

    Returns:
        None: Сохраняет результат в объекте config.
    """
    outcome = yield
    report = outcome.get_result()

    if report.when not in {"setup", "call"}:
        return

    log_path = _get_test_log_path(item.nodeid)
    if log_path is None:
        return

    file_log = item.config._test_file_logs[log_path]
    if report.when == "setup" and not report.skipped and not report.failed:
        return
    if report.when == "call" and report.skipped:
        return

    if report.passed:
        status = "PASSED"
        file_log["passed"] += 1
    elif report.failed:
        status = "FAILED"
        file_log["failed"] += 1
    else:
        status = "SKIPPED"
        file_log["skipped"] += 1

    entry = f"[{status}] {item.nodeid}"

    # Пользовательские детали из item._log_details (заполняются в тестах)
    log_details = getattr(item, "_log_details", [])
    if log_details:
        entry = "\n".join([entry, *log_details])

    if report.failed and report.longrepr:
        error_summary = _format_error_summary(report.longrepr)
        entry = f"{entry}\n{error_summary}"

    file_log["entries"].append(entry)
    file_log["entries"].append("")  # пустая строка-разделитель


def pytest_sessionfinish(session, exitstatus):
    """Записывает сводку и подробные результаты по каждому тестовому файлу.

    Args:
        session: Объект pytest-сессии.
        exitstatus: Код завершения pytest.

    Returns:
        None: Создаёт или обновляет лог-файлы в папке logs.
    """
    for log_path, results in session.config._test_file_logs.items():
        content = [
            f"Exit status: {exitstatus}",
            f"Passed: {results['passed']}",
            f"Failed: {results['failed']}",
            f"Skipped: {results['skipped']}",
            "",
            "Details:",
        ]
        if not results["entries"]:
            content.append("No tests were executed for this file in the current run.")
        content.extend(results["entries"])
        log_path.write_text("\n".join(content) + "\n", encoding="utf-8")
