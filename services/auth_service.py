import bcrypt
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from bson import ObjectId
from database import get_db
from utils import normalize_phone
from config import settings
import logging
import httpx

logger = logging.getLogger("app.auth_service")

# Custom exception for network-related errors (e.g., timeouts)
class NetworkError(Exception):
    """Raised when a network error such as a timeout occurs during online authentication."""
    pass

class AuthService:
    MOCK_SESSIONS = {}

    @staticmethod
    def hash_password(password: str) -> str:
        # bcrypt requires bytes
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except Exception:
            return False

    @staticmethod
    def create_user(user_data: Dict[str, Any]) -> str:
        db = get_db()
        
        # Validate unique phone
        phone_input = str(user_data.get("phone", "")).strip()
        if not phone_input:
            raise ValueError("Phone number is mandatory.")
        
        # Normalize unless it is the underscore sentinel
        phone = normalize_phone(phone_input)
        if phone != "_" and db.users.find_one({"phone": phone}):
            raise ValueError("Phone number is already registered.")
            
        user_data["phone"] = phone
        
        # Validate optional unique email
        email = user_data.get("email")
        if email and str(email).strip():
            email_clean = str(email).strip().lower()
            if "@" not in email_clean or "." not in email_clean.split("@")[-1]:
                raise ValueError("Email address must be a valid email format.")
            if db.users.find_one({"email": email_clean}):
                raise ValueError("Email address is already registered.")
            user_data["email"] = email_clean
        else:
            user_data.pop("email", None)

        # Hash password if provided
        if "password" in user_data:
            user_data["password_hash"] = AuthService.hash_password(user_data.pop("password"))
        
        user_data["created_at"] = datetime.now(timezone.utc)
        user_data["updated_at"] = datetime.now(timezone.utc)
        
        # Ensure status is active
        if "status" not in user_data:
            user_data["status"] = "active"
            
        result = db.users.insert_one(user_data)
        return str(result.inserted_id)

    @staticmethod
    def authenticate_user(search_term: str, password: str) -> Optional[Dict[str, Any]]:
        if settings.IS_LOCAL_OPERATOR:
            import httpx
            # 1. Try remote login first
            try:
                url = f"{settings.REMOTE_SERVER_URL}/api/auth/login"
                logger.info(f"Initiating online login request. Base URL: {settings.REMOTE_SERVER_URL}, Route: /api/auth/login, Method: POST")
                
                import time
                start_time = time.time()
                res = httpx.post(url, json={"username": search_term, "password": password}, timeout=httpx.Timeout(connect=5.0, read=20.0))
                elapsed = time.time() - start_time
                
                if res.status_code == 200:
                    logger.info(f"Online login succeeded. Status: 200 OK. Elapsed: {elapsed:.2f}s")
                    data = res.json()
                    user_data = data["user"]
                    
                    # Save user locally
                    from services.local_db import LocalDB
                    LocalDB.save_user(user_data)
                    
                    # Download initial snapshot
                    try:
                        snap_url = f"{settings.REMOTE_SERVER_URL}/api/sync/snapshot"
                        snap_res = httpx.post(snap_url, json={"operator_id": user_data["id"]}, timeout=10.0)
                        if snap_res.status_code == 200:
                            snap_data = snap_res.json()
                            for s in snap_data.get("schools", []):
                                LocalDB.save_school(s)
                            for p in snap_data.get("projects", []):
                                LocalDB.save_project(p)
                            for st in snap_data.get("students", []):
                                LocalDB.save_student(st)
                                
                            conn = LocalDB.get_connection()
                            try:
                                with conn:
                                    conn.execute("DELETE FROM student_photos")
                                    for ph in snap_data.get("student_photos", []):
                                        conn.execute("""
                                            INSERT INTO student_photos (id, student_id, original_filename, final_filename, relative_path, storage_type, version, status, captured_at, is_current)
                                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                        """, (
                                            ph["id"], ph["student_id"], ph["original_filename"],
                                            ph["final_filename"], ph["relative_path"], ph["storage_type"],
                                            ph["version"], ph["status"], ph["captured_at"], ph.get("is_current", 1)
                                        ))
                            finally:
                                conn.close()
                                
                            server_time = snap_data.get("server_time")
                            if server_time:
                                LocalDB.set_sync_metadata("last_downloaded_revision", server_time)
                    except Exception as se:
                        logger.error(f"Failed to download snapshot during online login: {se}")
                    
                    user_doc = user_data.copy()
                    user_doc["_id"] = user_doc["id"]
                    return user_doc
                else:
                    status = res.status_code
                    logger.warning(f"Online login failed. Base URL: {settings.REMOTE_SERVER_URL}, Route: /api/auth/login, Method: POST, Status: {status}, Elapsed: {elapsed:.2f}s")
                    if status == 401:
                        logger.warning("Reason: HTTP 401 Unauthorized. Invalid operator credentials.")
                    elif status == 403:
                        logger.warning("Reason: HTTP 403 Forbidden. Operator account is disabled.")
                    elif status == 404:
                        logger.warning("Reason: HTTP 404 Not Found. API route does not exist on remote server.")
                    elif status >= 500:
                        logger.warning("Reason: HTTP 5xx Server Error. Vercel backend or MongoDB database crashed.")
            except httpx.ConnectTimeout as cte:
                elapsed = time.time() - start_time
                logger.warning(f"Online login failed. Base URL: {settings.REMOTE_SERVER_URL}, Route: /api/auth/login, Method: POST, Exception: ConnectTimeout, Message: {cte}, Elapsed: {elapsed:.2f}s. Reason: Could not establish TCP connection to remote API within timeout.")
            except httpx.ReadTimeout as rte:
                elapsed = time.time() - start_time
                logger.warning(f"Online login failed. Base URL: {settings.REMOTE_SERVER_URL}, Route: /api/auth/login, Method: POST, Exception: ReadTimeout, Message: {rte}, Elapsed: {elapsed:.2f}s. Reason: Server accepted connection but timed out responding.")
            except httpx.ConnectError as ce:
                elapsed = time.time() - start_time
                err_msg = str(ce).lower()
                exc_type = "ConnectionError (DNS lookup failure)" if any(k in err_msg for k in ["dns", "getaddrinfo", "name", "resolve"]) else "ConnectionError (Connection refused)"
                logger.warning(f"Online login failed. Base URL: {settings.REMOTE_SERVER_URL}, Route: /api/auth/login, Method: POST, Exception: {exc_type}, Message: {ce}, Elapsed: {elapsed:.2f}s. Reason: Check remote server URL domain, port, and firewall rules.")
            except Exception as e:
                elapsed = time.time() - start_time
                logger.warning(f"Online login failed. Base URL: {settings.REMOTE_SERVER_URL}, Route: /api/auth/login, Method: POST, Exception: {type(e).__name__}, Message: {e}, Elapsed: {elapsed:.2f}s. Falling back to local SQLite.")
            
            # 2. Try local SQLite authentication
            from services.local_db import LocalDB
            user = LocalDB.get_user_by_term(search_term)
            if user and user.get("status") == "active":
                if AuthService.verify_password(password, user.get("password_hash", "")):
                    user["_id"] = str(user["id"])
                    if user.get("school_id"):
                        user["school_id"] = str(user["school_id"])
                    return user
        else:
            # Try database first
            try:
                db = get_db()
                phone_normalized = normalize_phone(search_term) if "@" not in search_term else search_term
                user = db.users.find_one({
                    "$or": [
                        {"email": search_term.lower()},
                        {"phone": phone_normalized}
                    ]
                })
                if user and user.get("status") == "active":
                    if AuthService.verify_password(password, user.get("password_hash", "")):
                        user["_id"] = str(user["_id"])
                        if user.get("school_id"):
                            user["school_id"] = str(user["school_id"])
                        return user
            except Exception:
                # Database offline fallback
                pass

        # Database offline or user not found, check mock fallback credentials
        if search_term in ["bloomgrapheteria@gmail.com", "9426407970"] and password in ["Swami@2003", "password123"]:
            # Seed mock user locally if IS_LOCAL_OPERATOR is enabled
            mock_user = {
                "_id": "mock_bloom_admin_id",
                "name": "Mock Bloom Admin",
                "email": "bloomgrapheteria@gmail.com",
                "phone": "9426407970",
                "role": "bloom_admin",
                "school_id": None,
                "status": "active",
                "password_hash": AuthService.hash_password("password123"),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            if settings.IS_LOCAL_OPERATOR:
                from services.local_db import LocalDB
                LocalDB.save_user(mock_user)
            return mock_user
        elif search_term in ["school@bloom.com", "1234567890"] and password in ["password123", "Swami@2003"]:
            mock_user = {
                "_id": "mock_school_admin_id",
                "name": "Mock School Admin",
                "email": "school@bloom.com",
                "phone": "1234567890",
                "role": "school_admin",
                "school_id": "mock_school_id",
                "status": "active",
                "password_hash": AuthService.hash_password("password123"),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            if settings.IS_LOCAL_OPERATOR:
                from services.local_db import LocalDB
                LocalDB.save_user(mock_user)
            return mock_user
        elif search_term in ["operator@bloom.com", "9876543210"] and password in ["password123"]:
            mock_user = {
                "_id": "mock_operator_id",
                "name": "Mock Operator",
                "email": "operator@bloom.com",
                "phone": "9876543210",
                "role": "bloom_operator",
                "school_id": None,
                "status": "active",
                "password_hash": AuthService.hash_password("password123"),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            if settings.IS_LOCAL_OPERATOR:
                from services.local_db import LocalDB
                LocalDB.save_user(mock_user)
            return mock_user

        return None

    @staticmethod
    def create_session(user_id: str, role: str, school_id: Optional[str] = None) -> str:
        session_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        
        session_doc = {
            "_id": session_id,
            "user_id": user_id,
            "role": role,
            "school_id": school_id,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc)
        }
        
        if settings.IS_LOCAL_OPERATOR:
            from services.local_db import LocalDB
            LocalDB.save_session(session_id, user_id, role, school_id, expires_at)
        else:
            try:
                db = get_db()
                db.sessions.insert_one(session_doc)
            except Exception:
                # Offline fallback
                AuthService.MOCK_SESSIONS[session_id] = session_doc
            
        return session_id

    @staticmethod
    def get_session(session_id: str) -> Optional[Dict[str, Any]]:
        if settings.IS_LOCAL_OPERATOR:
            from services.local_db import LocalDB
            session = LocalDB.get_session(session_id)
            if not session:
                return None
            
            # Check expiry
            expires_at = session.get("expires_at")
            if expires_at:
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > expires_at:
                    LocalDB.delete_session(session_id)
                    return None
            
            # Resolve user info
            user = LocalDB.get_user(session["user_id"])
            if not user:
                return None
                
            session["user"] = {
                "id": str(user["id"]),
                "name": user["name"],
                "email": user.get("email", ""),
                "role": user["role"],
                "school_id": str(user["school_id"]) if user.get("school_id") else None
            }
            return session
        else:
            session = None
            # Try DB lookup first
            try:
                db = get_db()
                session = db.sessions.find_one({"_id": session_id})
            except Exception:
                pass
                
            # Fallback to mock session dictionary
            if not session:
                session = AuthService.MOCK_SESSIONS.get(session_id)
                if not session:
                    return None
            
            # Check expiry
            expires_at = session.get("expires_at")
            if expires_at:
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > expires_at:
                    try:
                        db = get_db()
                        db.sessions.delete_one({"_id": session_id})
                    except Exception:
                        pass
                    AuthService.MOCK_SESSIONS.pop(session_id, None)
                    return None
                    
            # Resolve user info
            user = None
            user_id = session["user_id"]
            
            if user_id.startswith("mock_"):
                # Mock users
                if session["role"] == "bloom_admin":
                    user = {
                        "_id": "mock_bloom_admin_id",
                        "name": "Mock Bloom Admin",
                        "email": "bloomgrapheteria@gmail.com",
                        "role": "bloom_admin",
                        "school_id": None
                    }
                elif session["role"] == "school_admin":
                    user = {
                        "_id": "mock_school_admin_id",
                        "name": "Mock School Admin",
                        "email": "school@bloom.com",
                        "role": "school_admin",
                        "school_id": "mock_school_id"
                    }
                else:
                    user = {
                        "_id": "mock_operator_id",
                        "name": "Mock Operator",
                        "email": "operator@bloom.com",
                        "role": "bloom_operator",
                        "school_id": None
                    }
            else:
                try:
                    db = get_db()
                    user = db.users.find_one({"_id": ObjectId(user_id)})
                except Exception:
                    pass
                    
            if not user:
                return None
                
            session["user"] = {
                "id": str(user["_id"]),
                "name": user["name"],
                "email": user.get("email", ""),
                "role": user["role"],
                "school_id": str(user["school_id"]) if user.get("school_id") else None
            }
            return session

    @staticmethod
    def delete_session(session_id: str) -> None:
        if settings.IS_LOCAL_OPERATOR:
            from services.local_db import LocalDB
            LocalDB.delete_session(session_id)
        else:
            try:
                db = get_db()
                db.sessions.delete_one({"_id": session_id})
            except Exception:
                pass
            AuthService.MOCK_SESSIONS.pop(session_id, None)
