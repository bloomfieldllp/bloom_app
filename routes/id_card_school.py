import os
import io
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Request, Depends, Form, File, UploadFile, HTTPException, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from bson import ObjectId

from dependencies import RoleChecker
from services.school_service import SchoolService
from services.id_card_service import IdCardService
from services.google_drive_service import GoogleDriveService
from services.google_sheets_service import GoogleSheetsService
from database import get_db
from utils import get_templates

router = APIRouter(prefix="/school", dependencies=[Depends(RoleChecker(["school_admin"]))])
templates = get_templates()

@router.get("/verification", response_class=HTMLResponse)
@router.get("/id-cards", response_class=HTMLResponse)
async def school_verification_classes(
    request: Request,
    user = Depends(RoleChecker(["school_admin"]))
):
    school_id = user["school_id"]
    school = SchoolService.get_school(school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    progress = IdCardService.get_school_progress(school_id)
    fields = IdCardService.get_school_field_config(school_id)

    return templates.TemplateResponse(request=request, name="school/id_cards/classes.html", context={
        "user": user,
        "school": school,
        "progress": progress,
        "classes": progress["classes"],
        "correction_window": progress["correction_window"],
        "fields": fields,
        "msg": request.query_params.get("msg"),
        "error": request.query_params.get("error")
    })

@router.get("/verification/export")
@router.get("/id-cards/export")
async def export_school_corrections(
    user = Depends(RoleChecker(["school_admin"]))
):
    school_id = user["school_id"]
    excel_bytes, filename = GoogleSheetsService.generate_combined_school_excel(school_id)

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\""
        }
    )

@router.get("/verification/{class_name}", response_class=HTMLResponse)
@router.get("/id-cards/{class_name}", response_class=HTMLResponse)
async def school_class_id_cards(
    request: Request,
    class_name: str,
    mode: Optional[str] = "grid", # "grid" or "single"
    search: Optional[str] = None,
    status: Optional[str] = None,
    sort: Optional[str] = None,
    page: int = 1,
    limit: int = 1000,
    user = Depends(RoleChecker(["school_admin"]))
):
    school_id = user["school_id"]
    school = SchoolService.get_school(school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    cards, total = IdCardService.list_class_cards(
        school_id=school_id,
        class_name=class_name,
        search=search,
        status=status,
        sort=sort,
        page=page,
        limit=limit
    )

    fields = IdCardService.get_school_field_config(school_id)
    correction_window = IdCardService.get_correction_window(school_id)
    active_fields = [f for f in fields if f.get("enabled", True)]

    # Calculate class counts
    verified_count = sum(1 for c in cards if c.get("status") == "VERIFIED")
    correction_count = sum(1 for c in cards if c.get("status") in ["CORRECTION_REQUIRED", "PHOTO_WRONG"])
    pending_count = total - verified_count - correction_count
    if pending_count < 0:
        pending_count = 0

    is_htmx = request.headers.get("HX-Request") == "true"
    template_name = "school/id_cards/class_cards_partial.html" if is_htmx else "school/id_cards/class_view.html"

    return templates.TemplateResponse(request=request, name=template_name, context={
        "user": user,
        "school": school,
        "class_name": class_name,
        "cards": cards,
        "total": total,
        "verified_count": verified_count,
        "correction_count": correction_count,
        "pending_count": pending_count,
        "fields": fields,
        "active_fields": active_fields,
        "correction_window": correction_window,
        "mode": mode,
        "search": search or "",
        "status": status or "all",
        "sort": sort or "default",
        "page": page,
        "msg": request.query_params.get("msg"),
        "error": request.query_params.get("error")
    })

@router.get("/verification/card/{card_id}")
@router.get("/id-cards/card/{card_id}")
async def get_card_details(
    card_id: str,
    user = Depends(RoleChecker(["school_admin"]))
):
    school_id = user["school_id"]
    card = IdCardService.get_card_by_id(school_id, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="ID card record not found")

    fields = IdCardService.get_school_field_config(school_id)
    active_fields = [f for f in fields if f.get("enabled", True)]
    window = IdCardService.get_correction_window(school_id)

    return {
        "status": "success",
        "card": card,
        "fields": active_fields,
        "correction_window": window
    }

@router.get("/verification/image/{card_id}")
@router.get("/id-cards/image/{card_id}")
async def get_id_card_image(
    card_id: str,
    user = Depends(RoleChecker(["school_admin", "bloom_admin", "bloom_operator"]))
):
    db = get_db()
    card = db.id_card_records.find_one({"_id": ObjectId(card_id) if ObjectId.is_valid(card_id) else card_id})
    if not card:
        raise HTTPException(status_code=404, detail="ID card not found")

    # Authorize school access if school_admin
    if user["role"] == "school_admin" and str(card["school_id"]) != str(user["school_id"]):
        raise HTTPException(status_code=403, detail="Forbidden: Access Denied")

    school = db.schools.find_one({"_id": ObjectId(card["school_id"]) if ObjectId.is_valid(card["school_id"]) else card["school_id"]})
    school_name = school.get("name", card["school_id"]) if school else card["school_id"]

    file_stem = card.get("file_stem") or card.get("gr", "")
    res = GoogleDriveService.get_id_card_bytes(school_name, card.get("class_name", ""), file_stem)

    if not res:
        # Fallback SVG preview placeholder
        student_name = card.get("name", "Student")
        gr_no = card.get("gr", "N/A")
        std = card.get("standard", card.get("class_name", ""))
        svg_content = f"""<svg width="400" height="600" xmlns="http://www.w3.org/2000/svg">
            <rect width="400" height="600" rx="16" fill="#f8fafc" stroke="#e2e8f0" stroke-width="2"/>
            <rect x="0" y="0" width="400" height="80" rx="16" fill="#1e293b"/>
            <text x="200" y="50" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="20" font-weight="bold" fill="#ffffff" text-anchor="middle">{school_name}</text>
            <rect x="130" y="120" width="140" height="170" rx="12" fill="#e2e8f0" stroke="#cbd5e1" stroke-width="2"/>
            <circle cx="200" cy="180" r="35" fill="#94a3b8"/>
            <path d="M160 270 C160 230, 240 230, 240 270 Z" fill="#94a3b8"/>
            <text x="200" y="330" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="20" font-weight="bold" fill="#0f172a" text-anchor="middle">{student_name}</text>
            <text x="200" y="365" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="15" fill="#64748b" text-anchor="middle">Standard: {std}</text>
            <text x="200" y="395" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="15" fill="#64748b" text-anchor="middle">GR No: {gr_no}</text>
            <rect x="50" y="520" width="300" height="40" rx="8" fill="#f1f5f9"/>
            <text x="200" y="545" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="12" fill="#64748b" text-anchor="middle">COMPLETE GENERATED ID CARD PREVIEW</text>
        </svg>"""
        return Response(
            content=svg_content, 
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"}
        )

    img_bytes, content_type = res
    return Response(
        content=img_bytes, 
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400, immutable"}
    )

@router.post("/verification/verify")
@router.post("/id-cards/verify")
async def verify_card_action(
    card_id: str = Form(...),
    operation_id: Optional[str] = Form(None),
    user = Depends(RoleChecker(["school_admin"]))
):
    school_id = user["school_id"]
    try:
        res = IdCardService.verify_card(school_id, card_id, user_info=user.get("name"))
        return JSONResponse(content=res)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/verification/edit")
@router.post("/id-cards/edit")
async def edit_card_action(
    request: Request,
    card_id: str = Form(...),
    photo_wrong: Optional[str] = Form("false"),
    replacement_photo: Optional[UploadFile] = File(None),
    operation_id: Optional[str] = Form(None),
    user = Depends(RoleChecker(["school_admin"]))
):
    school_id = user["school_id"]
    form_data = await request.form()

    # Check photo wrong flag
    is_photo_wrong = str(photo_wrong).lower() in ["true", "1", "yes", "on"]

    # Read replacement photo bytes if uploaded
    photo_bytes = None
    photo_name = None
    if is_photo_wrong and replacement_photo and replacement_photo.filename:
        photo_bytes = await replacement_photo.read()
        photo_name = replacement_photo.filename
        if len(photo_bytes) > 15 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Replacement photo file size exceeds 15MB limit.")

    # Extract all configured / student values from form
    corrected_values = {}
    for k, v in form_data.items():
        if k not in ["card_id", "photo_wrong", "replacement_photo", "operation_id"]:
            corrected_values[k] = v

    try:
        res = IdCardService.submit_correction(
            school_id=school_id,
            card_id=card_id,
            corrected_values=corrected_values,
            photo_wrong=is_photo_wrong,
            replacement_photo_bytes=photo_bytes,
            replacement_photo_filename=photo_name,
            user_info=user.get("name")
        )
        return JSONResponse(content=res)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error submitting correction for card {card_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
