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
from routes import auth, admin, school, operator, sync
from dependencies import get_current_user

# Setup logging
log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=log_format)

try:
    from logging.handlers import RotatingFileHandler
    os.makedirs(settings.LOG_DIR, exist_ok=True)
    log_file = os.path.join(settings.LOG_DIR, "bloom.log")
    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(log_format))
    file_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(file_handler)
except Exception as le:
    print(f"Failed to initialize rotating file logger: {le}")

logger = logging.getLogger("app.main")

import platform

# Single Instance Lock Check
lock_file_path = os.path.join(os.path.dirname(settings.SQLITE_DB_PATH), "bloom.lock")
lock_file = None

def check_single_instance():
    global lock_file
    try:
        if os.path.exists(lock_file_path):
            try:
                os.remove(lock_file_path)
            except Exception:
                return False
        os.makedirs(os.path.dirname(lock_file_path), exist_ok=True)
        lock_file = open(lock_file_path, "w")
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        try:
            import msvcrt
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except Exception:
            pass
        return True
    except Exception:
        return False

def release_single_instance():
    global lock_file
    if lock_file:
        try:
            lock_file.close()
        except Exception:
            pass
        try:
            os.remove(lock_file_path)
        except Exception:
            pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    init_db()
    if not settings.IS_LOCAL_OPERATOR:
        try:
            from services.school_service import SchoolService
            SchoolService.auto_create_missing_hm_users()
        except Exception as e:
            logger.error(f"Failed to auto-create missing HM users: {e}")
    else:
        try:
            from services.sync_service import SyncService
            SyncService.start_service()
        except Exception as e:
            logger.error(f"Failed to start SyncService: {e}")
    yield
    # Shutdown actions
    if settings.IS_LOCAL_OPERATOR:
        try:
            from services.sync_service import SyncService
            SyncService.stop_service()
        except Exception:
            pass
    try:
        from services.file_watcher import WatcherService
        for pid in list(WatcherService._active_tasks.keys()):
            WatcherService.stop_watcher(pid)
    except Exception as e:
        logger.error(f"Error stopping file watchers: {e}")
    close_db()
    release_single_instance()


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
app.include_router(sync.router)


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

import traceback
import logging
from bson.errors import InvalidId

@app.exception_handler(InvalidId)
async def invalid_id_handler(request: Request, exc: InvalidId):
    logging.warning(f"Invalid ObjectId accessed: {request.url}")
    if request.headers.get("HX-Request") == "true":
        return HTMLResponse("<div class='alert alert-danger'>Invalid Resource ID</div>", status_code=400)
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=400, content={"detail": "Invalid Resource ID"})
    return templates.TemplateResponse(request=request, name="errors/400.html", context={"detail": "The requested resource identifier is invalid."}, status_code=400)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_id = str(uuid.uuid4())[:8]
    logging.error(f"Unhandled Server Error [ID: {error_id}] at {request.url.path}: {str(exc)}\n{traceback.format_exc()}")
    
    if request.headers.get("HX-Request") == "true":
        return HTMLResponse(f"<div class='alert alert-danger'>An unexpected error occurred (ID: {error_id}).</div>", status_code=500)
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error", "error_id": error_id})
    return templates.TemplateResponse(request=request, name="errors/500.html", context={"error_id": error_id}, status_code=500)

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
    
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


@app.get("/clear-students-db")
async def clear_students_db():
    db = get_db()
    student_count = db.students.count_documents({})
    photo_count = db.student_photos.count_documents({})
    
    db.students.delete_many({})
    db.student_photos.delete_many({})
    
    return {
        "status": "success",
        "cleared": {
            "students": student_count,
            "photos": photo_count
        }
    }


def wait_for_server(port: int, host: str = "127.0.0.1", timeout: float = 5.0) -> bool:
    import socket
    import time
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            time.sleep(0.1)
    return False

if __name__ == "__main__":
    import uvicorn
    import threading
    import sys
    import time
    
    # 1. Single Instance Check
    if not check_single_instance():
        import ctypes
        try:
            ctypes.windll.user32.MessageBoxW(
                0, 
                "BLOOM Operator is already running on this machine.", 
                "Application Already Active", 
                0x00000010 | 0x00000000  # MB_ICONERROR | MB_OK
            )
        except Exception:
            print("ERROR: BLOOM Operator is already running.")
        sys.exit(1)
        
    # 2. Run Uvicorn server programmatically (packaging-safe, passing the app object)
    port = 8010 if settings.IS_LOCAL_OPERATOR else 8000
    
    def start_server():
        try:
            config = uvicorn.Config(app, host="127.0.0.1", port=port, reload=False, log_level="warning")
            server = uvicorn.Server(config)
            server.run()
        except Exception as e:
            logger.error(f"Uvicorn server crashed: {e}")
            
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    
    # 3. Wait until the local server is actually listening
    server_ready = wait_for_server(port)
    if not server_ready:
        logger.error("FastAPI server failed to start within timeout.")
        import ctypes
        try:
            ctypes.windll.user32.MessageBoxW(
                0, 
                "Failed to initialize the local server. Please check the logs.", 
                "Server Startup Error", 
                0x00000010 | 0x00000000  # MB_ICONERROR | MB_OK
            )
        except Exception:
            print("ERROR: FastAPI server failed to start.")
        sys.exit(1)
        
    # 4. Native Desktop Window (WebView2)
    run_desktop_window = getattr(sys, 'frozen', False) or os.environ.get("BLOOM_DESKTOP") == "true" or platform.system() == "Windows"
    
    if run_desktop_window:
        try:
            import webview
            
            # Open native window
            webview.create_window(
                title="BLOOM Operator Panel",
                url=f"http://127.0.0.1:{port}",
                width=1280,
                height=820,
                resizable=True,
                min_size=(1024, 768)
            )
            webview.start()
        except Exception as we:
            logger.error(f"Failed to start WebView2 window: {we}. Falling back to default browser.")
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{port}")
            try:
                server_thread.join()
            except KeyboardInterrupt:
                pass
    else:
        import webbrowser
        try:
            webbrowser.open(f"http://127.0.0.1:{port}")
        except Exception:
            pass
        try:
            server_thread.join()
        except KeyboardInterrupt:
            pass
