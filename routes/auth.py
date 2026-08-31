from fastapi import APIRouter, Request, Response, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from services.auth_service import AuthService, NetworkError
import logging
logger = logging.getLogger("app.auth_route")

router = APIRouter()
templates = get_templates()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # If already logged in, redirect to respective dashboard
    session_cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if session_cookie:
        session = AuthService.get_session(session_cookie)
        if session:
            role = session["user"]["role"]
            if role == "bloom_admin":
                return RedirectResponse(url="/admin", status_code=303)
            elif role == "school_admin":
                return RedirectResponse(url="/school", status_code=303)
            elif role == "bloom_operator":
                return RedirectResponse(url="/operator", status_code=303)
                
    return templates.TemplateResponse(request=request, name="auth/login.html", context={"error": None})

@router.post("/login")
async def login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...)
):
    try:
        user = AuthService.authenticate_user(username, password)
    except NetworkError as ne:
        logger.warning(f"Network error during authentication: {ne}")
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={"error": "Unable to reach the online authentication server. Please check your connection or try again."}
        )
    if not user:
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={"error": "Invalid email/phone or password"}
        )
    
    # Create session
    session_id = AuthService.create_session(
        user_id=user["_id"],
        role=user["role"],
        school_id=user.get("school_id")
    )
    

    redirect_resp = RedirectResponse(url="/loader", status_code=303)
    redirect_resp.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        max_age=86400, # 24 hours
        samesite="lax",
        secure=False # set True in production with SSL
    )
    return redirect_resp

@router.get("/logout")
async def logout(request: Request, response: Response):
    session_cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if session_cookie:
        AuthService.delete_session(session_cookie)
        
    redirect_resp = RedirectResponse(url="/login", status_code=303)
    redirect_resp.delete_cookie(key=settings.SESSION_COOKIE_NAME)
    return redirect_resp
