import os
import io
import csv
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional
from bson import ObjectId
from database import get_db

class StudentImportService:
    @staticmethod
    def parse_file_preview(file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """
        Parses the uploaded file to extract headers and the first 5 preview rows.
        """
        ext = os.path.splitext(filename)[1].lower()
        if ext == '.csv':
            # Try to detect encoding or default to utf-8 with fallback to latin-1
            try:
                content = file_bytes.decode('utf-8')
            except UnicodeDecodeError:
                content = file_bytes.decode('latin-1')
            
            # Read sample lines
            f = io.StringIO(content)
            reader = csv.reader(f)
            headers = next(reader, [])
            rows = []
            for i, row in enumerate(reader):
                if i >= 5:
                    break
                # pad or slice row to match headers length
                if len(row) < len(headers):
                    row += [""] * (len(headers) - len(row))
                else:
                    row = row[:len(headers)]
                rows.append(row)
            
            # Count total rows
            f.seek(0)
            next(reader, []) # skip header
            total_rows = sum(1 for _ in reader)
            
        elif ext in ['.xlsx', '.xls']:
            f_io = io.BytesIO(file_bytes)
            # engine openpyxl handles xlsx, xlrd handles xls
            engine = "openpyxl" if ext == ".xlsx" else None
            df = pd.read_excel(f_io, engine=engine)
            headers = [str(c) for c in df.columns]
            rows_raw = df.head(5).values.tolist()
            rows = []
            for r in rows_raw:
                rows.append([str(val) if not pd.isna(val) else "" for val in r])
            total_rows = len(df)
        else:
            raise ValueError("Unsupported file format. Please upload CSV or Excel (.xlsx, .xls) files.")
            
        return {
            "filename": filename,
            "headers": headers,
            "preview_rows": rows,
            "total_rows": total_rows
        }

    @staticmethod
    def validate_and_parse_records(
        file_bytes: bytes, 
        filename: str, 
        mapping: Dict[str, str], 
        project_id: str,
        school_id: str = None
    ) -> Dict[str, Any]:
        """
        Parses all records from the file based on column mapping, and performs validations:
        - Check for required columns mapping (GR, Name, Standard)
        - Detect missing required fields per row
        - Detect duplicate GR numbers within the uploaded file
        Parses CSV/Excel file, applies column mapping, normalizes GRs,
        and validates against existing records in the database.
        """
        db = get_db()
        if not school_id:
            project = db.projects.find_one({"_id": ObjectId(project_id)})
            if project:
                school_id = str(project.get("school_id"))
            
        ext = os.path.splitext(filename)[1].lower()
        if ext == '.csv':
            try:
                content = file_bytes.decode('utf-8')
            except UnicodeDecodeError:
                content = file_bytes.decode('latin-1')
            df = pd.read_csv(io.StringIO(content))
        elif ext in ['.xlsx', '.xls']:
            engine = "openpyxl" if ext == ".xlsx" else None
            df = pd.read_excel(io.BytesIO(file_bytes), engine=engine)
        else:
            raise ValueError(f"Unsupported file format for {filename}. CSV/Excel only.")
            
        df.columns = [str(c).strip() for c in df.columns]
        
        # Mapping
        gr_col = mapping.get("gr")
        name_col = mapping.get("name")
        std_col = mapping.get("standard")
        roll_col = mapping.get("roll_number")
        div_col = mapping.get("division")
        
        if not gr_col or not name_col:
            raise ValueError("GR Number and Name columns are required mapping fields.")
            
        if gr_col not in df.columns or name_col not in df.columns:
            raise ValueError("Mapped columns not found in uploaded file.")
            
        valid_records = []
        duplicate_gr_in_file = {}
        missing_name_count = 0
        missing_gr_count = 0
        missing_std_count = 0
        
        # Find existing GRs in DB for this school
        if school_id:
            existing_students = list(db.students.find({"school_id": school_id}, {"gr": 1}))
        else:
            existing_students = list(db.students.find({"project_id": project_id}, {"gr": 1}))
        existing_grs = {s["gr"] for s in existing_students}
        
        duplicate_gr_in_db = set()
        seen_grs_in_file = {}
        
        def clean_val(val) -> str:
            if pd.isna(val) or val is None:
                return ""
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                if isinstance(val, float) and val.is_integer():
                    return str(int(val))
                elif isinstance(val, float):
                    return str(int(val))
                return str(int(val))
            val_str = str(val).strip()
            if val_str.endswith(".0"):
                return val_str[:-2]
            return val_str

        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            
            # Fetch target values using clean_val to strip .0 decimal suffixes
            gr_val = clean_val(row_dict.get(gr_col))
            name_val = clean_val(row_dict.get(name_col))
            std_val = clean_val(row_dict.get(std_col)) if std_col else ""
            roll_val = clean_val(row_dict.get(roll_col)) if roll_col else ""
            div_val = clean_val(row_dict.get(div_col)) if div_col else ""
            
            # Row raw data should preserve original keys and clean up nan values
            raw_data = {k: (v if not pd.isna(v) else "") for k, v in row_dict.items()}
            
            # Validations
            has_error = False
            if not gr_val:
                missing_gr_count += 1
                has_error = True
            if not name_val:
                missing_name_count += 1
                has_error = True
                
            if has_error:
                continue
                
            # Check duplicate in file
            if gr_val in seen_grs_in_file:
                if gr_val not in duplicate_gr_in_file:
                    duplicate_gr_in_file[gr_val] = [seen_grs_in_file[gr_val]]
                duplicate_gr_in_file[gr_val].append(idx + 1)
                continue
            
            seen_grs_in_file[gr_val] = idx + 1
            
            # Check duplicate in DB
            if gr_val in existing_grs:
                duplicate_gr_in_db.add(gr_val)
            
            # Construct standard record
            valid_records.append({
                "gr": gr_val,
                "name": name_val,
                "standard": std_val,
                "roll_number": roll_val,
                "division": div_val,
                "raw_data": raw_data,
                "photo_status": "not_captured"
            })
            
        return {
            "total_rows": len(df),
            "valid_records": valid_records,
            "duplicate_gr_in_file_count": len(duplicate_gr_in_file),
            "duplicate_gr_in_file": duplicate_gr_in_file,
            "duplicate_gr_in_db_count": len(duplicate_gr_in_db),
            "duplicate_gr_in_db": list(duplicate_gr_in_db),
            "missing_name_count": missing_name_count,
            "missing_gr_count": missing_gr_count,
            "missing_std_count": missing_std_count
        }

    @staticmethod
    def execute_import(
        school_id: str,
        project_id: str,
        valid_records: List[Dict[str, Any]],
        action: str
    ) -> Dict[str, int]:
        """
        Executes database import based on selected action:
        - 'replace': Deletes all existing students in this project first, then imports.
        - 'update': Inserts new, updates existing student records by matching GR.
        - 'add_only': Only imports records whose GR does not already exist in the database.
        """
        db = get_db()
        now = datetime.now(timezone.utc)
        
        inserted_count = 0
        updated_count = 0
        deleted_count = 0
        
        if action == "replace":
            # Delete existing students ONLY in this project
            del_result = db.students.delete_many({"project_id": project_id})
            deleted_count = del_result.deleted_count
            
            for r in valid_records:
                gr_val = r["gr"]
                existing = db.students.find_one({"school_id": school_id, "gr": gr_val})
                if existing:
                    # Update fields and move to this project
                    db.students.update_one(
                        {"_id": existing["_id"]},
                        {
                            "$set": {
                                "name": r["name"],
                                "standard": r["standard"],
                                "roll_number": r["roll_number"],
                                "division": r["division"],
                                "raw_data": r["raw_data"],
                                "project_id": project_id,
                                "updated_at": now
                            }
                        }
                    )
                    inserted_count += 1
                else:
                    r["school_id"] = school_id
                    r["project_id"] = project_id
                    r["created_at"] = now
                    r["updated_at"] = now
                    db.students.insert_one(r)
                    inserted_count += 1
                
        elif action == "update":
            # For each record, if exists in school+gr, update fields, else insert
            for r in valid_records:
                gr_val = r["gr"]
                existing = db.students.find_one({"school_id": school_id, "gr": gr_val})
                if existing:
                    # Update fields (except photo_status and created_at to avoid wiping operator progress)
                    # Also update project_id if it changed
                    db.students.update_one(
                        {"_id": existing["_id"]},
                        {
                            "$set": {
                                "name": r["name"],
                                "standard": r["standard"],
                                "roll_number": r["roll_number"],
                                "division": r["division"],
                                "raw_data": r["raw_data"],
                                "project_id": project_id,
                                "updated_at": now
                            }
                        }
                    )
                    updated_count += 1
                else:
                    r["school_id"] = school_id
                    r["project_id"] = project_id
                    r["created_at"] = now
                    r["updated_at"] = now
                    db.students.insert_one(r)
                    inserted_count += 1
                    
        elif action == "add_only":
            # Find existing GRs in DB for this school
            existing_students = list(db.students.find({"school_id": school_id}, {"gr": 1}))
            existing_grs = {s["gr"] for s in existing_students}
            
            records_to_insert = []
            for r in valid_records:
                if r["gr"] not in existing_grs:
                    r["school_id"] = school_id
                    r["project_id"] = project_id
                    r["created_at"] = now
                    r["updated_at"] = now
                    records_to_insert.append(r)
                    
            if records_to_insert:
                db.students.insert_many(records_to_insert)
                inserted_count = len(records_to_insert)
                
        else:
            raise ValueError(f"Unknown import action: {action}")
            
        return {
            "inserted": inserted_count,
            "updated": updated_count,
            "deleted": deleted_count
        }

    @staticmethod
    def combine_multiple_files(files: List[Tuple[bytes, str]]) -> Tuple[bytes, List[str], List[List[str]], int]:
        """
        Combines multiple CSV or Excel files into a single CSV string representation.
        Returns a tuple of: (combined_csv_bytes, headers, preview_rows, total_rows)
        """
        dfs = []
        for file_bytes, filename in files:
            if not file_bytes:
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext == '.csv':
                try:
                    content = file_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    content = file_bytes.decode('latin-1')
                df = pd.read_csv(io.StringIO(content))
            elif ext in ['.xlsx', '.xls']:
                engine = "openpyxl" if ext == ".xlsx" else None
                df = pd.read_excel(io.BytesIO(file_bytes), engine=engine)
            else:
                raise ValueError(f"Unsupported file format for {filename}. CSV/Excel only.")
            
            # Clean dataframe column names to string
            df.columns = [str(c).strip() for c in df.columns]
            dfs.append(df)
            
        if not dfs:
            raise ValueError("No valid student data files uploaded.")
            
        # Concatenate and fill NaN
        combined_df = pd.concat(dfs, ignore_index=True, sort=False).fillna("")
        
        # Write combined to CSV bytes
        out_buf = io.StringIO()
        combined_df.to_csv(out_buf, index=False)
        csv_bytes = out_buf.getvalue().encode('utf-8')
        
        headers = [str(c) for c in combined_df.columns]
        rows_raw = combined_df.head(5).values.tolist()
        preview_rows = []
        for r in rows_raw:
            preview_rows.append([str(val) for val in r])
            
        return csv_bytes, headers, preview_rows, len(combined_df)
