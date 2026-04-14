from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import get_engine
from src.sql_layer.pipeline import CANNOT_ANSWER


def _make_app(mock_engine):
    """Создаёт приложение с подменённой зависимостью подключения к БД.

    Args:
        mock_engine: Мок-объект SQLAlchemy engine для тестов.

    Returns:
        object: Экземпляр FastAPI-приложения с переопределённой зависимостью.
    """
    app = create_app()
    app.dependency_overrides[get_engine] = lambda: mock_engine
    return app


def _mock_engine_ok():
    """Создаёт mock engine с успешным выполнением SQL-запроса.

    Args:
        None: Функция не принимает аргументы.

    Returns:
        MagicMock: Настроенный mock engine, возвращающий две строки результата.
    """
    result = MagicMock()
    result.fetchall.return_value = [(1,), (2,)]
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value = result
    engine = MagicMock()
    engine.connect.return_value = conn
    return engine


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


def test_health_ok():
    """Проверяет успешный ответ health endpoint при доступной БД.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет HTTP-ответ через assert.
    """
    engine = _mock_engine_ok()
    app = _make_app(engine)
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["db_reachable"] is True


def test_health_db_unreachable():
    """Проверяет признак недоступности БД в ответе health endpoint.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет HTTP-ответ через assert.
    """
    engine = MagicMock()
    engine.connect.side_effect = Exception("connection refused")
    app = _make_app(engine)
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["db_reachable"] is False


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------


def _patch_agent_ask(return_value: dict):
    """Создаёт patch для AgentFlow.ask с заданным возвращаемым значением.

    Args:
        return_value (dict): Значение, которое должен вернуть agent.ask().

    Returns:
        patch: Объект patch для src.agent.sql_flow.AgentFlow.ask.
    """
    return patch(
        "src.agent.sql_flow.AgentFlow.ask",
        new=AsyncMock(return_value=return_value),
    )


def test_chat_returns_ok_with_rows():
    """Проверяет успешный ответ chat endpoint при наличии строк результата.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет HTTP-ответ через assert.
    """
    engine = _mock_engine_ok()
    app = _make_app(engine)

    with _patch_agent_ask(
        {"answer": "Тестовый ответ", "status": "ok", "sql_rows_count": 2}
    ):
        with TestClient(app) as client:
            r = client.post("/chat", json={"question": "Сколько объектов?"})

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["sql_rows_count"] == 2
    assert data["answer"] == "Тестовый ответ"


def test_chat_returns_cannot_answer():
    """Проверяет статус cannot_answer при отказе SQL-пайплайна.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет HTTP-ответ через assert.
    """
    engine = _mock_engine_ok()
    app = _make_app(engine)

    with _patch_agent_ask(
        {"answer": CANNOT_ANSWER, "status": "cannot_answer",
         "sql_rows_count": None}
    ):
        with TestClient(app) as client:
            r = client.post("/chat", json={"question": "xyz"})

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "cannot_answer"
    assert data["sql_rows_count"] is None


def test_chat_returns_error_on_pipeline_error():
    """Проверяет статус error при возврате строки ошибки из пайплайна.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет HTTP-ответ через assert.
    """
    engine = _mock_engine_ok()
    app = _make_app(engine)

    error_msg = "Ошибка после 3 попыток: something"
    with _patch_agent_ask(
        {"answer": error_msg, "status": "error", "sql_rows_count": None}
    ):
        with TestClient(app) as client:
            r = client.post("/chat", json={"question": "q"})

    assert r.status_code == 200
    assert r.json()["status"] == "error"


def test_chat_validates_empty_question():
    """Проверяет валидацию пустого вопроса в запросе chat.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет HTTP-ответ через assert.
    """
    engine = _mock_engine_ok()
    app = _make_app(engine)
    with TestClient(app) as client:
        r = client.post("/chat", json={"question": ""})
    assert r.status_code == 422


def test_chat_validates_too_long_question():
    """Проверяет валидацию слишком длинного вопроса в запросе chat.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет HTTP-ответ через assert.
    """
    engine = _mock_engine_ok()
    app = _make_app(engine)
    with TestClient(app) as client:
        r = client.post("/chat", json={"question": "x" * 2001})
    assert r.status_code == 422
