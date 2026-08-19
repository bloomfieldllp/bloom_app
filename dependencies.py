from fastapi import Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from services.auth_service import AuthService
from config import settings

def get_current_user(request: Request):
    session_cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_cookie:
        return None
    session = AuthService.get_session(session_cookie)
    if not session:
        return None
    return session["user"]

def require_auth(request: Request):
    user = get_current_user(request)
    if not user:
        # Redirect to login page for UI routing
        raise HTTPException(status_code=307, headers={"Location": "/login"})
    return user

class RoleChecker:
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, request: Request):
        user = get_current_user(request)
        if not user:
            raise HTTPException(status_code=307, headers={"Location": "/login"})
            
        if user["role"] not in self.allowed_roles:
            raise HTTPException(status_code=403, detail="Forbidden: Access Denied")
            
        return user
