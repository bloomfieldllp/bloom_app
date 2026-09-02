import io
import pandas as pd
from typing import List, Dict, Any, Tuple
from database import get_db

class StudentImportService:
    @staticmethod
    def read_excel_headers(files_data: List[Tuple[bytes, str]]) -> Tuple[List[str], bytes]:
        if not files_data:
            raise ValueError("No file provided.")
        content, filename = files_data[0]
        try:
            df = pd.read_excel(io.BytesIO(content), nrows=10)
        except Exception:
            raise ValueError("Failed to read Excel file. Please ensure it is a valid .xlsx or .xls file.")
            
        # Clean headers
        headers = []
        for col in df.columns:
            if not str(col).startswith("Unnamed"):
                headers.append(str(col).strip())
        return headers, content

    @staticmethod
    def parse_mapped_records(file_bytes: bytes, mapping: Dict[str, str], school_id: str) -> Dict[str, Any]:
        try:
            df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)
        except Exception:
            raise ValueError("Failed to parse Excel data.")
            
        # Drop rows where all mapped columns are NaN
        mapped_cols = [col for col in mapping.values() if col in df.columns]
        df.dropna(subset=mapped_cols, how='all', inplace=True)
        
        db = get_db()
        existing_students = list(db.students.find({"school_id": school_id}, {"gr": 1}))
        existing_grs = {str(s["gr"]).strip().lower() for s in existing_students if s.get("gr")}
        
        valid_records = []
        duplicate_gr_in_file = {}
        duplicate_gr_in_db = {}
        missing_gr_count = 0
        missing_name_count = 0
        
        seen_grs_in_file = {}
        
        for idx, row in df.iterrows():
            record = {}
            # Core fields
            gr_col = mapping.get("gr")
            name_col = mapping.get("name")
            
            gr_val = str(row[gr_col]).strip() if gr_col and gr_col in df.columns and pd.notna(row[gr_col]) else ""
            name_val = str(row[name_col]).strip() if name_col and name_col in df.columns and pd.notna(row[name_col]) else ""
            
            if not gr_val:
                missing_gr_count += 1
                continue
            if not name_val:
                missing_name_count += 1
                continue
                
            record["gr"] = gr_val
            record["name"] = name_val
            
            # Other standard fields
            for std_field in ["dob", "address", "contact", "class_name", "division", "gender", "roll_number"]:
                col = mapping.get(std_field)
                if col and col in df.columns and pd.notna(row[col]):
                    record[std_field] = str(row[col]).strip()
            
            # Map standard aliases
            if "class_name" in record:
                record["standard"] = record["class_name"]
            if "division" in record:
                record["section"] = record["division"]
                
            # Custom fields
            custom_fields = {}
            for map_key, col in mapping.items():
                if map_key.startswith("custom_") and col in df.columns and pd.notna(row[col]):
                    field_key = map_key.replace("custom_", "", 1)
                    custom_fields[field_key] = str(row[col]).strip()
                    
            if custom_fields:
                record["custom_fields"] = custom_fields
                
            gr_lower = gr_val.lower()
            if gr_lower in existing_grs:
                if gr_val not in duplicate_gr_in_db:
                    duplicate_gr_in_db[gr_val] = []
                duplicate_gr_in_db[gr_val].append(record)
            elif gr_lower in seen_grs_in_file:
                if gr_val not in duplicate_gr_in_file:
                    duplicate_gr_in_file[gr_val] = [seen_grs_in_file[gr_lower]]
                duplicate_gr_in_file[gr_val].append(record)
            else:
                seen_grs_in_file[gr_lower] = record
                valid_records.append(record)
                
        return {
            "total_rows": len(valid_records) + missing_gr_count + missing_name_count + sum(len(v) for v in duplicate_gr_in_file.values()),
            "valid_records": valid_records,
            "duplicate_gr_in_file_count": len(duplicate_gr_in_file),
            "duplicate_gr_in_file": duplicate_gr_in_file,
            "duplicate_gr_in_db_count": len(duplicate_gr_in_db),
            "duplicate_gr_in_db": duplicate_gr_in_db,
            "missing_gr_count": missing_gr_count,
            "missing_name_count": missing_name_count,
            "missing_std_count": 0
        }

    @staticmethod
    def manual_execute_import(school_id: str, project_id: str, valid_records: List[Dict[str, Any]], action: str) -> Dict[str, int]:
        from datetime import datetime, timezone
        from bson import ObjectId
        db = get_db()
        now = datetime.now(timezone.utc)
        
        inserted = 0
        updated = 0
        
        # Action semantics:
        # replace: Delete all existing students for this project, then insert new.
        # append: Insert all valid records.
        # update: If GR exists, update. If not, insert.
        
        if action == "replace":
            db.students.delete_many({"project_id": project_id})
            
        for rec in valid_records:
            gr = rec["gr"]
            
            doc = {
                "name": rec["name"],
                "gr": gr,
                "project_id": project_id,
                "school_id": school_id,
                "updated_at": now
            }
            
            for f in ["dob", "address", "contact", "standard", "section", "roll_number", "gender", "custom_fields"]:
                if f in rec:
                    doc[f] = rec[f]
                    
            if action == "append" or action == "replace":
                doc["_id"] = ObjectId()
                doc["photo_status"] = "not_captured"
                db.students.insert_one(doc)
                inserted += 1
            elif action == "update":
                # Find existing by GR and school_id
                existing = db.students.find_one({"gr": gr, "school_id": school_id})
                if existing:
                    # Update
                    db.students.update_one({"_id": existing["_id"]}, {"$set": doc})
                    updated += 1
                else:
                    doc["_id"] = ObjectId()
                    doc["photo_status"] = "not_captured"
                    db.students.insert_one(doc)
                    inserted += 1
                    
        return {"inserted": inserted, "updated": updated}