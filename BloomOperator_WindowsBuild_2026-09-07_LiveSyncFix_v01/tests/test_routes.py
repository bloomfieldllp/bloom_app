import pytest
from fastapi.testclient import TestClient
from main import app
import os

client = TestClient(app)

def test_login_page_renders():
    response = client.get("/login")
    assert response.status_code == 200
    assert "form" in response.text.lower()

def test_protected_route_without_auth():
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code in [302, 303, 307] # Should redirect to login

# I will write a mock-based test suite for the requested routes
from unittest.mock import patch, MagicMock

@patch("database.get_db")
def test_preview_invalid_project_id(mock_get_db):
    # Test Invalid ObjectId via global error handler
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db
    # Create fake session token or bypass auth
    # For a true integration test in FastAPI with Depends, we can override dependencies
    pass
