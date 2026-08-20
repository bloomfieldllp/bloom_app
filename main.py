import os
import logging
from contextlib import asynccontextmanager
import bson

# Keep a reference to the original ObjectId class
OriginalObjectId = bson.ObjectId

# Monkeypatch bson.ObjectId globally to handle non-valid hex strings gracefully (e.g. mock_school_id)
class SafeObjectId(OriginalObjectId):
    def __new__(cls, oid=None):
        if oid is None:
            return OriginalObjectId()
        if isinstance(oid, OriginalObjectId):
            return oid
        try:
            return OriginalObjectId(oid)
        except Exception:
            import hashlib
            h = hashlib.md5(str(oid).encode('utf-8')).hexdigest()[:24]
            return OriginalObjectId(h)
bson.ObjectId = SafeObjectId

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import settings
from database import init_db, close_db
from routes import auth, admin, school, operator
from dependencies import get_current_user

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bloom_app")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    init_db()
    yield
    # Shutdown actions
    try:
        from services.file_watcher import WatcherService
        for pid in list(WatcherService._active_tasks.keys()):
            WatcherService.stop_watcher(pid)
    except Exception as e:
        logger.error(f"Error stopping file watchers: {e}")
    close_db()

app = FastAPI(
    title="Bloom ID Card Platform",
    description="Phase 1 Bloom ID-Card Photography Management Platform",
    version="1.0.0",
    lifespan=lifespan
)

from utils import get_resource_path, get_templates

# Mount static files
app.mount("/static", StaticFiles(directory=get_resource_path("static")), name="static")
templates = get_templates()

# Include Routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(school.router)
app.include_router(operator.router)

@app.get("/")
async def root(request: Request):
    """
    Root route: redirects to /loader if authenticated, else to /login
    """
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return RedirectResponse(url="/loader", status_code=303)

@app.get("/loader")
async def get_loader(request: Request):
    """
    Renders loader screen if authenticated, else redirects to login page
    """
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request=request, name="loader.html", context={})

@app.get("/api/user/destination")
async def user_destination(request: Request):
    """
    Helper API for loader script to know where to redirect the user after animation is complete
    """
    user = get_current_user(request)
    if not user:
        return {"redirect_url": "/login"}
    
    role = user["role"]
    if role == "bloom_admin":
        return {"redirect_url": "/admin"}
    elif role == "school_admin":
        return {"redirect_url": "/school"}
    elif role == "bloom_operator":
        return {"redirect_url": "/operator"}
    
    return {"redirect_url": "/login"}

# Exception handlers
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 403:
        return templates.TemplateResponse(
            request=request, 
            name="errors/403.html", 
            context={"detail": exc.detail}, 
            status_code=403
        )
    if exc.status_code == 404:
        return templates.TemplateResponse(
            request=request, 
            name="errors/404.html", 
            context={"detail": exc.detail}, 
            status_code=404
        )
    raise exc


if __name__ == "__main__":
    import uvicorn
    import webbrowser
    import threading
    import time
    
    # Auto-open operator dashboard browser window after 1 second
    def launch_browser():
        time.sleep(1.2)
        try:
            webbrowser.open("http://127.0.0.1:8000")
        except Exception:
            pass
            
    threading.Thread(target=launch_browser, daemon=True).start()
    
    # Run production Uvicorn server
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
