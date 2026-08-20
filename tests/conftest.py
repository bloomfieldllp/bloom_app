import pytest
import mongomock
from fastapi.testclient import TestClient
import database
from main import app as fastapi_app

@pytest.fixture(autouse=True)
def mock_db(monkeypatch):
    mock_client = mongomock.MongoClient()
    mock_db = mock_client["bloom_test"]
    
    # Mock database global connection state
    monkeypatch.setattr(database, "client", mock_client)
    monkeypatch.setattr(database, "db", mock_db)
    from config import settings
    monkeypatch.setattr(settings, "IS_LOCAL_OPERATOR", False)
    
    database.init_db()
    yield mock_db
    
    database.close_db()

@pytest.fixture
def client():
    # Use standard FastAPI TestClient
    with TestClient(fastapi_app) as c:
        yield c
