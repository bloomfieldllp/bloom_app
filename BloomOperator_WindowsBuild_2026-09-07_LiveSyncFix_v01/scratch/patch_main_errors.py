with open("main.py", "r") as f:
    content = f.read()

import re

# Add Exception handlers
new_handlers = """
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
"""

content = content.replace("@app.exception_handler(HTTPException)", new_handlers)

with open("main.py", "w") as f:
    f.write(content)

