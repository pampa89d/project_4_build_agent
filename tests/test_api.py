from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import get_engine
from src.sql_layer.pipeline import CANNOT_ANSWER

VALID_SQL = "SELECT id FROM works"


def _make_app(mock_engine):
    app = create_app()
    app.dependency_overrides[get_engine] = lambda: mock_engine
    return app


def _mock_engine_ok():
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
    engine = _mock_engine_ok()
    app = _make_app(engine)
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["db_reachable"] is True


def test_health_db_unreachable():
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


FAKE_MESSAGES = [{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}]


def _patch_pipeline(sql_result, answer="Тестовый ответ"):
    return (
        patch("src.api.routes.build_messages", return_value=FAKE_MESSAGES),
        patch("src.api.routes.execute_sql_query", return_value=sql_result),
        patch("src.api.routes.generate_answer", return_value=answer),
    )


def test_chat_returns_ok_with_rows():
    engine = _mock_engine_ok()
    app = _make_app(engine)

    patches = _patch_pipeline(sql_result=[(1,), (2,)])
    with patches[0], patches[1], patches[2]:
        with TestClient(app) as client:
            r = client.post("/chat", json={"question": "Сколько объектов?"})

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["sql_rows_count"] == 2
    assert data["answer"] == "Тестовый ответ"


def test_chat_returns_cannot_answer():
    engine = _mock_engine_ok()
    app = _make_app(engine)

    patches = _patch_pipeline(sql_result=CANNOT_ANSWER, answer=CANNOT_ANSWER)
    with patches[0], patches[1], patches[2]:
        with TestClient(app) as client:
            r = client.post("/chat", json={"question": "xyz"})

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "cannot_answer"
    assert data["sql_rows_count"] is None


def test_chat_returns_error_on_pipeline_error():
    engine = _mock_engine_ok()
    app = _make_app(engine)

    error_msg = "Ошибка после попытки исправления: something"
    patches = _patch_pipeline(sql_result=error_msg, answer=error_msg)
    with patches[0], patches[1], patches[2]:
        with TestClient(app) as client:
            r = client.post("/chat", json={"question": "q"})

    assert r.status_code == 200
    assert r.json()["status"] == "error"


def test_chat_validates_empty_question():
    engine = _mock_engine_ok()
    app = _make_app(engine)
    with TestClient(app) as client:
        r = client.post("/chat", json={"question": ""})
    assert r.status_code == 422


def test_chat_validates_too_long_question():
    engine = _mock_engine_ok()
    app = _make_app(engine)
    with TestClient(app) as client:
        r = client.post("/chat", json={"question": "x" * 2001})
    assert r.status_code == 422
