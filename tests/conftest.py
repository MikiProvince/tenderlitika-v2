import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///./test.db")

import main as app_module  # noqa: E402


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app_module.app.dependency_overrides.clear()
    yield
    app_module.app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app_module.app) as test_client:
        yield test_client
