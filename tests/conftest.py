import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that require a real LLM API key",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration (requires real LLM, skipped by default)",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-integration"):
        skip_integration = pytest.mark.skip(
            reason="Pass --run-integration to run LLM integration tests"
        )
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)
