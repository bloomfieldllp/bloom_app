import os
import io
import json
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from database import get_db

logger = logging.getLogger("app.google_sheets")

class GoogleSheetsService:
    """
    Google Sheets & Combined Excel Service for School ID Card Correction Logs.
    
    Provides:
    1. Live Correction Logging: Idempotent upserting of correction records.
    2. Combined School Excel Generation: Exporting a unified, styled workbook containing
       all correction records across all classes for offline Photoshop workflow.
    """

    CORE_COLUMNS = [
        "School",
        "Class",
        "Original File Name",
        "Student ID / Mapping Key",
        "Student Name",
        "GR Number",
        "Standard",
        "Phone Number",
        "Address",
        "DOB",
        "PAN Number"
    ]

    SUFFIX_COLUMNS = [
        "Correction Type",
        "Photo Wrong",
        "Replacement Photo File Name",
        "Correction Status",
        "Timestamp",
        "Last Updated"
    ]

    @classmethod
    def get_columns_for_school(cls, school_id: str) -> List[str]:
        """
        Determines the full column list dynamically for a school,
        including any custom configured fields.
        """
        db = get_db()
        from bson import ObjectId
        school = None
        try:
            school = db.schools.find_one({"_id": ObjectId(school_id) if ObjectId.is_valid(school_id) else school_id})
        except Exception:
            pass
            
        custom_cols = []
        if school and "id_card_config" in school:
            cfg_fields = school["id_card_config"].get("fields", [])
            for f in cfg_fields:
                label = f.get("label") or f.get("key")
                if label not in cls.CORE_COLUMNS and label not in cls.SUFFIX_COLUMNS:
                    custom_cols.append(label)
                    
        return cls.CORE_COLUMNS + custom_cols + cls.SUFFIX_COLUMNS

    @classmethod
    def upsert_correction_log(
        cls,
        school_id: str,
        class_name: str,
        correction_data: Dict[str, Any],
        user_info: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Idempotently logs a correction record into the database's live correction collection.
        Also keeps a record ready for Google Sheets synchronization.
        """
        db = get_db()
        now = datetime.now(timezone.utc)
        
        file_stem = correction_data.get("file_stem", "").strip().lower()
        original_filename = correction_data.get("original_filename", "")
        student_id = str(correction_data.get("student_id", ""))
        
        log_doc = {
            "school_id": str(school_id),
            "class_name": str(class_name),
            "original_filename": original_filename,
            "file_stem": file_stem,
            "student_id": student_id,
            "student_name": correction_data.get("name", ""),
            "gr": correction_data.get("gr", ""),
            "standard": correction_data.get("standard", ""),
            "phone": correction_data.get("phone", ""),
            "address": correction_data.get("address", ""),
            "dob": correction_data.get("date_of_birth", "") or correction_data.get("dob", ""),
            "pan_number": correction_data.get("pan_number", ""),
            "father_name": correction_data.get("father_name", ""),
            "mother_name": correction_data.get("mother_name", ""),
            "blood_group": correction_data.get("blood_group", ""),
            "custom_values": correction_data.get("custom_values", {}),
            "correction_type": correction_data.get("correction_type", "DETAIL_EDITED"),
            "photo_wrong": "Yes" if correction_data.get("photo_wrong") else "No",
            "replacement_photo_filename": correction_data.get("replacement_photo_filename") or "",
            "correction_status": "CORRECTION_REQUIRED",
            "updated_by": user_info or "School Admin",
            "last_updated": now.isoformat()
        }

        # Idempotent Upsert by (school_id, class_name, file_stem)
        query = {
            "school_id": str(school_id),
            "class_name": str(class_name),
            "file_stem": file_stem
        }
        
        existing = db.id_card_corrections.find_one(query)
        if not existing:
            log_doc["created_at"] = now.isoformat()
            db.id_card_corrections.insert_one(log_doc)
        else:
            db.id_card_corrections.update_one(query, {"$set": log_doc})
            
        logger.info(f"Correction log upserted for {school_id} - {class_name} - {original_filename}")
        return log_doc

    @classmethod
    def generate_combined_school_excel(cls, school_id: str) -> Tuple[bytes, str]:
        """
        Generates a combined Excel file containing all ID Card correction records across all classes.
        Filename format: "{School Name} — All ID Card Corrections.xlsx"
        """
        db = get_db()
        from bson import ObjectId
        
        school_name = "School"
        try:
            school = db.schools.find_one({"_id": ObjectId(school_id) if ObjectId.is_valid(school_id) else school_id})
            if school:
                school_name = school.get("name", "School")
        except Exception:
            pass

        corrections = list(db.id_card_corrections.find({"school_id": str(school_id)}).sort([
            ("class_name", 1),
            ("gr", 1),
            ("student_name", 1)
        ]))

        columns = cls.get_columns_for_school(school_id)
        
        # Build rows
        rows_data = []
        for c in corrections:
            row = {
                "School": school_name,
                "Class": c.get("class_name", ""),
                "Original File Name": c.get("original_filename", ""),
                "Student ID / Mapping Key": c.get("student_id", "") or c.get("file_stem", ""),
                "Student Name": c.get("student_name", ""),
                "GR Number": c.get("gr", ""),
                "Standard": c.get("standard", ""),
                "Phone Number": c.get("phone", ""),
                "Address": c.get("address", ""),
                "DOB": c.get("dob", ""),
                "PAN Number": c.get("pan_number", ""),
                "Correction Type": c.get("correction_type", ""),
                "Photo Wrong": c.get("photo_wrong", "No"),
                "Replacement Photo File Name": c.get("replacement_photo_filename", ""),
                "Correction Status": c.get("correction_status", "CORRECTION_REQUIRED"),
                "Timestamp": c.get("created_at", c.get("last_updated", "")),
                "Last Updated": c.get("last_updated", "")
            }
            # Custom values
            custom_vals = c.get("custom_values", {})
            for k, v in custom_vals.items():
                row[k] = str(v)
                
            rows_data.append(row)

        df = pd.DataFrame(rows_data, columns=columns) if rows_data else pd.DataFrame(columns=columns)

        # Style with openpyxl
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='ID Card Corrections')
            ws = writer.sheets['ID Card Corrections']

            # Header styling
            header_fill = PatternFill(start_color="1A1917", end_color="1A1917", fill_type="solid")
            header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
            border = Border(
                left=Side(style='thin', color='EAE8E1'),
                right=Side(style='thin', color='EAE8E1'),
                top=Side(style='thin', color='EAE8E1'),
                bottom=Side(style='thin', color='EAE8E1')
            )

            for col_idx, col_name in enumerate(columns, 1):
                cell = ws.cell(row=1, column=col_idx)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

                # Column width
                max_len = max([len(str(val)) for val in df[col_name]] + [len(col_name)]) if not df.empty else len(col_name)
                ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = min(max(max_len + 4, 14), 45)

            # Data rows styling
            for row_idx in range(2, len(rows_data) + 2):
                for col_idx in range(1, len(columns) + 1):
                    cell = ws.cell(row=row_idx, column=col_idx)
                    cell.border = border
                    cell.font = Font(name="Calibri", size=10)
                    if columns[col_idx - 1] in ["Correction Type", "Photo Wrong", "Correction Status"]:
                        cell.alignment = Alignment(horizontal="center", vertical="center")
                        if cell.value == "Yes":
                            cell.font = Font(name="Calibri", size=10, bold=True, color="DC2626")

        excel_bytes = output.getvalue()
        clean_name = school_name.replace("/", "_").replace("\\", "_").replace("—", "-").strip()
        filename = f"{clean_name} - All ID Card Corrections.xlsx"
        return excel_bytes, filename
