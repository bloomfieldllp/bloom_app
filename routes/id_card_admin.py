import json
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Request, Depends, Form, HTTPException, Response, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from bson import ObjectId

from dependencies import RoleChecker
from services.school_service import SchoolService
from services.id_card_service import IdCardService, PREDEFINED_FIELDS
from services.google_sheets_service import GoogleSheetsService
from database import get_db
from utils import get_templates

router = APIRouter(prefix="/admin", dependencies=[Depends(RoleChecker(["bloom_admin"]))])
templates = get_templates()
import logging

logger = logging.getLogger("app.id_card_admin")

@router.get("/id-cards", response_class=HTMLResponse)
async def admin_id_cards_overview(
    request: Request,
    user = Depends(RoleChecker(["bloom_admin"]))
):
    try:
        schools = SchoolService.list_schools()
        school_stats = []
        
        for s in schools:
            sid = str(s["_id"])
            prog = IdCardService.get_school_progress(sid)
            school_stats.append({
                "school": s,
                "progress": prog
            })

        return templates.TemplateResponse(request=request, name="admin/id_cards/overview.html", context={
            "user": user,
            "school_stats": school_stats,
            "msg": request.query_params.get("msg"),
            "error": request.query_params.get("error")
        })
    except Exception as e:
        logger.error(f"Failed to load admin ID cards overview: {e}", exc_info=True)
        return templates.TemplateResponse(request=request, name="admin/id_cards/overview.html", context={
            "user": user,
            "school_stats": [],
            "error": f"Error loading ID card data: {str(e)}"
        })

@router.get("/schools/{school_id}/id-card-config", response_class=HTMLResponse)
async def school_id_card_config_page(
    request: Request,
    school_id: str,
    user = Depends(RoleChecker(["bloom_admin"]))
):
    school = SchoolService.get_school(school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    fields = IdCardService.get_school_field_config(school_id)
    window = IdCardService.get_correction_window(school_id)

    return templates.TemplateResponse(request=request, name="admin/id_cards/config.html", context={
        "user": user,
        "school": school,
        "fields": fields,
        "predefined_fields": PREDEFINED_FIELDS,
        "correction_window": window,
        "msg": request.query_params.get("msg"),
        "error": request.query_params.get("error")
    })

@router.post("/schools/{school_id}/id-card-config")
async def save_school_id_card_config(
    request: Request,
    school_id: str,
    user = Depends(RoleChecker(["bloom_admin"]))
):
    form_data = await request.form()
    
    # 1. Check if JSON payload was sent
    fields_raw = form_data.get("fields_json")
    if fields_raw:
        try:
            fields = json.loads(fields_raw)
            IdCardService.save_school_field_config(school_id, fields)
            return RedirectResponse(
                url=f"/admin/schools/{school_id}/id-card-config?msg=ID+Card+fields+saved+successfully",
                status_code=303
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid fields format: {str(e)}")

    # 2. Or parse standard form submit
    field_keys = form_data.getlist("field_key")
    field_labels = form_data.getlist("field_label")
    field_types = form_data.getlist("field_type")
    field_enabled_keys = set(form_data.getlist("field_enabled"))

    fields = []
    for idx, key in enumerate(field_keys, 1):
        if not key:
            continue
        label = field_labels[idx - 1] if idx - 1 < len(field_labels) else key.title()
        ftype = field_types[idx - 1] if idx - 1 < len(field_types) else "text"
        is_enabled = key in field_enabled_keys
        is_predefined = any(p["key"] == key for p in PREDEFINED_FIELDS)

        fields.append({
            "key": key,
            "label": label,
            "type": ftype,
            "enabled": is_enabled,
            "order": idx,
            "is_predefined": is_predefined
        })

    IdCardService.save_school_field_config(school_id, fields)
    return RedirectResponse(
        url=f"/admin/schools/{school_id}/id-card-config?msg=Configuration+updated+successfully",
        status_code=303
    )

@router.get("/schools/{school_id}/correction-window", response_class=HTMLResponse)
async def school_correction_window_page(
    request: Request,
    school_id: str,
    user = Depends(RoleChecker(["bloom_admin"]))
):
    school = SchoolService.get_school(school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    window = IdCardService.get_correction_window(school_id)

    # Format for datetime-local input (YYYY-MM-DDTHH:MM)
    start_val = ""
    if window.get("start_datetime"):
        start_val = window["start_datetime"][:16]
    end_val = ""
    if window.get("end_datetime"):
        end_val = window["end_datetime"][:16]

    return templates.TemplateResponse(request=request, name="admin/id_cards/window.html", context={
        "user": user,
        "school": school,
        "correction_window": window,
        "start_val": start_val,
        "end_val": end_val,
        "msg": request.query_params.get("msg"),
        "error": request.query_params.get("error")
    })

@router.post("/schools/{school_id}/correction-window")
async def save_school_correction_window(
    school_id: str,
    start_datetime: Optional[str] = Form(None),
    end_datetime: Optional[str] = Form(None),
    user = Depends(RoleChecker(["bloom_admin"]))
):
    IdCardService.save_correction_window(school_id, start_datetime, end_datetime)
    return RedirectResponse(
        url=f"/admin/schools/{school_id}/correction-window?msg=Correction+window+updated+successfully",
        status_code=303
    )

@router.get("/schools/{school_id}/id-card-progress", response_class=HTMLResponse)
async def school_id_card_progress_page(
    request: Request,
    school_id: str,
    user = Depends(RoleChecker(["bloom_admin"]))
):
    school = SchoolService.get_school(school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    progress = IdCardService.get_school_progress(school_id)
    
    db = get_db()
    corrections = list(db.id_card_corrections.find({"school_id": str(school_id)}).sort("last_updated", -1))
    for c in corrections:
        c["id"] = str(c["_id"])
        c["_id"] = str(c["_id"])

    history = list(db.id_card_correction_history.find({"school_id": str(school_id)}).sort("timestamp", -1).limit(50))
    for h in history:
        h["id"] = str(h["_id"])
        h["_id"] = str(h["_id"])

    return templates.TemplateResponse(request=request, name="admin/id_cards/progress.html", context={
        "user": user,
        "school": school,
        "progress": progress,
        "classes": progress["classes"],
        "corrections": corrections,
        "history": history,
        "correction_window": progress["correction_window"],
        "msg": request.query_params.get("msg"),
        "error": request.query_params.get("error")
    })

@router.post("/schools/{school_id}/id-cards/index-drive")
async def trigger_drive_index(
    school_id: str,
    class_name: Optional[str] = Form(None),
    user = Depends(RoleChecker(["bloom_admin"]))
):
    from services.google_drive_service import GoogleDriveService
    school = SchoolService.get_school(school_id)
    if school:
        GoogleDriveService.sync_school_from_google_drive(school.get("name", ""), school_id)
        GoogleDriveService.sync_school_from_google_drive(school.get("school_code", ""), school_id)

    if class_name:
        res = IdCardService.index_class_cards(school_id, class_name)
    else:
        # Index all classes
        classes = IdCardService.list_school_classes(school_id)
        for c in classes:
            IdCardService.index_class_cards(school_id, c["class_name"])
            
    return RedirectResponse(
        url=f"/admin/schools/{school_id}/id-card-progress?msg=ID+Cards+successfully+indexed+from+storage",
        status_code=303
    )

@router.get("/schools/{school_id}/id-cards/export")
async def admin_export_school_corrections(
    school_id: str,
    user = Depends(RoleChecker(["bloom_admin"]))
):
    excel_bytes, filename = GoogleSheetsService.generate_combined_school_excel(school_id)

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\""
        }
    )

@router.get("/schools/{school_id}/upload-cards", response_class=HTMLResponse)
async def school_upload_cards_page(
    request: Request,
    school_id: str,
    user = Depends(RoleChecker(["bloom_admin"]))
):
    school = SchoolService.get_school(school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    classes = IdCardService.list_school_classes(school_id)
    
    return templates.TemplateResponse(request=request, name="admin/id_cards/upload.html", context={
        "user": user,
        "school": school,
        "classes": classes,
        "msg": request.query_params.get("msg"),
        "error": request.query_params.get("error")
    })

@router.post("/schools/{school_id}/upload-cards")
async def handle_school_upload_cards(
    school_id: str,
    files: List[UploadFile] = File(...),
    excel_file: Optional[UploadFile] = File(None),
    default_class: Optional[str] = Form(None),
    file_paths: Optional[List[str]] = Form(None),
    user = Depends(RoleChecker(["bloom_admin"]))
):
    school = SchoolService.get_school(school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    excel_bytes = None
    if excel_file and excel_file.filename:
        excel_bytes = await excel_file.read()

    file_tuples = []
    for idx, f in enumerate(files):
        if not f.filename:
            continue
        path_name = f.filename
        if file_paths and idx < len(file_paths) and file_paths[idx]:
            path_name = file_paths[idx]
        content = await f.read()
        file_tuples.append((path_name, content))

    res = IdCardService.import_and_upload_id_cards(
        school_id=school_id,
        files=file_tuples,
        excel_file_bytes=excel_bytes,
        default_class_name=default_class
    )

    msg = res.get("message", "Upload completed successfully")
    return RedirectResponse(
        url=f"/admin/schools/{school_id}/id-card-progress?msg={msg}",
        status_code=303
    )

@router.post("/schools/{school_id}/upload-roster")
async def handle_upload_roster(
    school_id: str,
    excel_file: UploadFile = File(...),
    default_class: Optional[str] = Form(None),
    user = Depends(RoleChecker(["bloom_admin"]))
):
    school = SchoolService.get_school(school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    excel_bytes = await excel_file.read()
    count = IdCardService.import_roster_spreadsheet(school_id, excel_bytes, default_class)
    return JSONResponse({
        "status": "success",
        "imported_count": count,
        "message": f"Successfully mapped {count} student records from roster spreadsheet"
    })

@router.post("/schools/{school_id}/upload-card-chunk")
async def handle_upload_card_chunk(
    school_id: str,
    files: List[UploadFile] = File(...),
    file_paths: Optional[List[str]] = Form(None),
    default_class: Optional[str] = Form(None),
    user = Depends(RoleChecker(["bloom_admin"]))
):
    school = SchoolService.get_school(school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    saved_count = 0
    ignored_count = 0
    touched_classes = set()

    for idx, f in enumerate(files):
        if not f.filename:
            continue
        path_name = f.filename
        if file_paths and idx < len(file_paths) and file_paths[idx]:
            path_name = file_paths[idx]
        content = await f.read()
        res = IdCardService.save_single_card_image(
            school_id=school_id,
            filepath_or_name=path_name,
            file_bytes=content,
            default_class_name=default_class
        )
        if res.get("ignored"):
            ignored_count += 1
        else:
            saved_count += 1
            if res.get("class_name"):
                touched_classes.add(res["class_name"])

    return JSONResponse({
        "status": "success",
        "saved_count": saved_count,
        "ignored_count": ignored_count,
        "touched_classes": sorted(list(touched_classes))
    })

@router.post("/schools/{school_id}/finalize-upload")
async def handle_finalize_upload(
    request: Request,
    school_id: str,
    user = Depends(RoleChecker(["bloom_admin"]))
):
    school = SchoolService.get_school(school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    try:
        body = await request.json()
        classes = body.get("classes", [])
    except Exception:
        classes = []

    if not classes:
        # Index all school classes
        all_c = IdCardService.list_school_classes(school_id)
        classes = [c["class_name"] for c in all_c]

    indexed_summary = {}
    for c in classes:
        idx_res = IdCardService.index_class_cards(school_id, c)
        indexed_summary[c] = idx_res.get("total", 0)

    total_indexed = sum(indexed_summary.values())
    msg = f"Successfully uploaded and indexed {total_indexed} ID cards across {len(classes)} classes."
    
    return JSONResponse({
        "status": "success",
        "message": msg,
        "indexed_summary": indexed_summary,
        "redirect_url": f"/admin/schools/{school_id}/id-card-progress?msg={msg}"
    })

