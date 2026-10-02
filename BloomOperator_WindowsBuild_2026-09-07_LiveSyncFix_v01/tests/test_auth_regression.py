"""
Tests for the authentication regression fix.
Verifies:
- Vercel (IS_LOCAL_OPERATOR=False) does NOT call its own /api/auth/login
- Vercel authentication uses MongoDB directly
- Windows client (IS_LOCAL_OPERATOR=True) with internet uses remote login
- Windows client without internet uses local SQLite
- Invalid credentials are handled correctly (return None, not crash)
- Network timeout does not crash the client
- Mock users are NOT available in production
"""
import pytest
from unittest.mock import patch, MagicMock
from services.auth_service import AuthService, NetworkError
from config import settings


class TestVercelAuthPath:
    """Tests for the production Vercel authentication path (IS_LOCAL_OPERATOR=False)."""

    def test_vercel_does_not_self_call(self, mock_db, monkeypatch):
        """Verify Vercel auth path queries MongoDB directly, never makes HTTP requests."""
        monkeypatch.setattr(settings, "IS_LOCAL_OPERATOR", False)

        with patch("services.auth_service.httpx") as mock_httpx:
            # Create a user in mock MongoDB
            AuthService.create_user({
                "name": "Test User",
                "phone": "9876543210",
                "email": "test@example.com",
                "password": "testpassword",
                "role": "school_admin",
                "school_id": "65cb76e27ad5bcf341999999",
                "status": "active"
            })
            result = AuthService.authenticate_user("test@example.com", "testpassword")

            # httpx.post should NEVER be called on the Vercel path
            mock_httpx.post.assert_not_called()
            assert result is not None
            assert result["email"] == "test@example.com"

    def test_vercel_uses_mongodb_directly(self, mock_db, monkeypatch):
        """Verify Vercel auth goes through MongoDB, not HTTP."""
        monkeypatch.setattr(settings, "IS_LOCAL_OPERATOR", False)

        # Insert a user directly in the mock DB
        AuthService.create_user({
            "name": "DB User",
            "phone": "1111122222",
            "email": "dbuser@example.com",
            "password": "dbpassword",
            "role": "bloom_admin",
            "status": "active"
        })

        user = AuthService.authenticate_user("dbuser@example.com", "dbpassword")
        assert user is not None
        assert user["name"] == "DB User"
        assert user["role"] == "bloom_admin"

    def test_vercel_invalid_credentials_returns_none(self, mock_db, monkeypatch):
        """Invalid credentials on Vercel return None (not a crash)."""
        monkeypatch.setattr(settings, "IS_LOCAL_OPERATOR", False)

        AuthService.create_user({
            "name": "Real User",
            "phone": "3333344444",
            "email": "real@example.com",
            "password": "correctpassword",
            "role": "school_admin",
            "school_id": "65cb76e27ad5bcf341999999",
            "status": "active"
        })

        result = AuthService.authenticate_user("real@example.com", "wrongpassword")
        assert result is None

    def test_vercel_nonexistent_user_returns_none(self, mock_db, monkeypatch):
        """Non-existent user on Vercel returns None (not a crash)."""
        monkeypatch.setattr(settings, "IS_LOCAL_OPERATOR", False)

        result = AuthService.authenticate_user("nonexistent@example.com", "anypassword")
        assert result is None

    def test_vercel_mock_users_not_available(self, mock_db, monkeypatch):
        """Mock users must NOT be accessible on Vercel (production)."""
        monkeypatch.setattr(settings, "IS_LOCAL_OPERATOR", False)

        # These are the mock user credentials — they should NOT work in production
        result = AuthService.authenticate_user("bloomgrapheteria@gmail.com", "password123")
        assert result is None

        result = AuthService.authenticate_user("school@bloom.com", "password123")
        assert result is None

        result = AuthService.authenticate_user("operator@bloom.com", "password123")
        assert result is None

    def test_vercel_db_failure_does_not_crash(self, monkeypatch):
        """If MongoDB is unavailable on Vercel, authenticate_user returns None without crashing."""
        monkeypatch.setattr(settings, "IS_LOCAL_OPERATOR", False)

        import database
        def broken_get_db():
            raise Exception("MongoDB connection failed")
        monkeypatch.setattr(database, "db", None)
        monkeypatch.setattr(database, "client", None)
        monkeypatch.setattr("services.auth_service.get_db", broken_get_db)

        # Should return None, not raise an exception
        result = AuthService.authenticate_user("anyone@example.com", "anypassword")
        assert result is None


class TestWindowsRemoteLogin:
    """Tests for the Windows client remote login path (IS_LOCAL_OPERATOR=True, internet available)."""

    def test_windows_uses_remote_login_when_online(self, monkeypatch):
        """Windows client with internet should POST to REMOTE_SERVER_URL."""
        monkeypatch.setattr(settings, "IS_LOCAL_OPERATOR", True)
        monkeypatch.setattr(settings, "REMOTE_SERVER_URL", "https://bloom-app-orcin.vercel.app")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "user": {
                "id": "remote_user_1",
                "name": "Remote User",
                "email": "remote@example.com",
                "phone": "5555566666",
                "role": "bloom_operator",
                "school_id": None,
                "status": "active",
                "password_hash": "hashed"
            }
        }

        mock_local_db = MagicMock()
        with patch("httpx.post", return_value=mock_response) as mock_post, \
             patch.dict("sys.modules", {"services.local_db": MagicMock(LocalDB=mock_local_db)}):

            result = AuthService.authenticate_user("remote@example.com", "remotepassword")

            # Verify httpx.post was called — first call should be to /api/auth/login
            assert mock_post.call_count >= 1
            first_call_url = mock_post.call_args_list[0][0][0]
            assert "bloom-app-orcin.vercel.app" in first_call_url
            assert "/api/auth/login" in first_call_url

            assert result is not None
            assert result["_id"] == "remote_user_1"

    def test_windows_remote_login_invalid_credentials(self, monkeypatch):
        """Windows client: remote returns 401 → falls through to SQLite (returns None if no local user)."""
        monkeypatch.setattr(settings, "IS_LOCAL_OPERATOR", True)
        monkeypatch.setattr(settings, "REMOTE_SERVER_URL", "https://bloom-app-orcin.vercel.app")

        mock_response = MagicMock()
        mock_response.status_code = 401

        mock_local_db_cls = MagicMock()
        mock_local_db_cls.get_user_by_term.return_value = None

        with patch("httpx.post", return_value=mock_response), \
             patch.dict("sys.modules", {"services.local_db": MagicMock(LocalDB=mock_local_db_cls)}):

            result = AuthService.authenticate_user("wrong@example.com", "wrongpassword")
            assert result is None


class TestWindowsOfflineFallback:
    """Tests for the Windows client offline fallback (IS_LOCAL_OPERATOR=True, no internet)."""

    def test_windows_falls_back_to_sqlite_on_timeout(self, monkeypatch):
        """Network timeout → falls back to local SQLite auth."""
        import httpx as httpx_module
        monkeypatch.setattr(settings, "IS_LOCAL_OPERATOR", True)
        monkeypatch.setattr(settings, "REMOTE_SERVER_URL", "https://bloom-app-orcin.vercel.app")

        local_user = {
            "id": "local_user_1",
            "name": "Local User",
            "email": "local@example.com",
            "phone": "7777788888",
            "role": "bloom_operator",
            "school_id": None,
            "status": "active",
            "password_hash": AuthService.hash_password("localpassword")
        }

        mock_local_db_cls = MagicMock()
        mock_local_db_cls.get_user_by_term.return_value = local_user

        with patch("httpx.post", side_effect=httpx_module.ReadTimeout("read timed out")), \
             patch.dict("sys.modules", {"services.local_db": MagicMock(LocalDB=mock_local_db_cls)}):

            result = AuthService.authenticate_user("local@example.com", "localpassword")
            assert result is not None
            assert result["_id"] == "local_user_1"

    def test_windows_falls_back_to_sqlite_on_connect_error(self, monkeypatch):
        """Connection error → falls back to local SQLite auth."""
        import httpx as httpx_module
        monkeypatch.setattr(settings, "IS_LOCAL_OPERATOR", True)
        monkeypatch.setattr(settings, "REMOTE_SERVER_URL", "https://bloom-app-orcin.vercel.app")

        local_user = {
            "id": "local_user_2",
            "name": "Offline User",
            "email": "offline@example.com",
            "phone": "4444455555",
            "role": "bloom_operator",
            "school_id": None,
            "status": "active",
            "password_hash": AuthService.hash_password("offlinepass")
        }

        mock_local_db_cls = MagicMock()
        mock_local_db_cls.get_user_by_term.return_value = local_user

        with patch("httpx.post", side_effect=httpx_module.ConnectError("Connection refused")), \
             patch.dict("sys.modules", {"services.local_db": MagicMock(LocalDB=mock_local_db_cls)}):

            result = AuthService.authenticate_user("offline@example.com", "offlinepass")
            assert result is not None
            assert result["_id"] == "local_user_2"

    def test_windows_network_timeout_does_not_crash(self, monkeypatch):
        """Network timeout with no local user → returns None, does not crash."""
        import httpx as httpx_module
        monkeypatch.setattr(settings, "IS_LOCAL_OPERATOR", True)
        monkeypatch.setattr(settings, "REMOTE_SERVER_URL", "https://bloom-app-orcin.vercel.app")

        mock_local_db_cls = MagicMock()
        mock_local_db_cls.get_user_by_term.return_value = None

        with patch("httpx.post", side_effect=httpx_module.ReadTimeout("read timed out")), \
             patch.dict("sys.modules", {"services.local_db": MagicMock(LocalDB=mock_local_db_cls)}):

            # Should return None (no local user), not raise an exception
            result = AuthService.authenticate_user("nobody@example.com", "anypassword")
            assert result is None


class TestLoginRoute:
    """Tests for the POST /login route exception handling."""

    def test_login_invalid_credentials_shows_error(self, client, mock_db):
        """Invalid credentials show error message, not a server crash."""
        resp = client.post("/login", data={"username": "fake@test.com", "password": "wrong"})
        assert resp.status_code == 200
        assert "Invalid email/phone or password" in resp.text

    def test_login_db_error_shows_error(self, client, monkeypatch):
        """Database failure during login shows error message, not FUNCTION_INVOCATION_FAILED."""
        monkeypatch.setattr(settings, "IS_LOCAL_OPERATOR", False)

        with patch.object(AuthService, "authenticate_user", side_effect=Exception("DB crashed")):
            resp = client.post("/login", data={"username": "test@test.com", "password": "test"})
            assert resp.status_code == 500
            assert "An internal error occurred" in resp.text

    def test_login_network_error_shows_friendly_message(self, client, monkeypatch):
        """NetworkError shows friendly connectivity message."""
        monkeypatch.setattr(settings, "IS_LOCAL_OPERATOR", False)

        with patch.object(AuthService, "authenticate_user", side_effect=NetworkError("Connection refused")):
            resp = client.post("/login", data={"username": "test@test.com", "password": "test"})
            assert resp.status_code == 200
            assert "Unable to reach the online authentication server" in resp.text
