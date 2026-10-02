import os
import argparse
import sys
import csv
import re
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Any

# Add the parent directory to sys.path to import services
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import settings
from services.local_db import LocalDB

def get_expected_filename(student: dict, version: int = 1) -> str:
    std = student.get("standard") or student.get("class_name") or ""
    div = student.get("division") or student.get("section") or ""
    roll = student.get("roll_number", "")
    name = student.get("name", "")
    gr = student.get("gr", "")
    
    name_clean = re.sub(r'[^a-zA-Z0-9\s-]', '', name)
    name_clean = re.sub(r'[\s-]+', '_', name_clean).strip('_')
    
    if std:
        div_clean = re.sub(r'(?i)division\s*', '', div).strip()
        class_sec = f"{std}{div_clean}"
        roll_padded = f"{int(roll):03d}" if roll and str(roll).isdigit() else str(roll or "000")
        base_name = f"{class_sec}_{roll_padded}_{name_clean}"
    else:
        base_name = f"{gr}_{name_clean}" if gr else name_clean
        
    return f"{base_name}_v{version}.jpg" if version > 1 else f"{base_name}.jpg"

def main():
    parser = argparse.ArgumentParser(description="Reconcile existing photos with the local database.")
    parser.add_argument("--project_id", required=True, help="Project ID to reconcile")
    parser.add_argument("--final_folder", required=True, help="Path to the final photo folder to scan")
    parser.add_argument("--execute", action="store_true", help="Actually modify the database (default is DRY-RUN)")
    parser.add_argument("--report", default="reconciliation_report.csv", help="Path to save the CSV report")
    args = parser.parse_args()

    project_id = args.project_id
    final_folder = args.final_folder
    is_dry_run = not args.execute
    report_path = args.report

    print(f"=== PHOTO RECONCILIATION TOOL ===")
    print(f"Mode: {'DRY-RUN' if is_dry_run else 'EXECUTE (Modifying DB)'}")
    print(f"Project ID: {project_id}")
    print(f"Folder: {final_folder}\n")

    if not os.path.isdir(final_folder):
        print(f"Error: Folder {final_folder} does not exist.")
        sys.exit(1)

    # 1. Fetch students
    students = LocalDB.list_students(project_id)
    if not students:
        print(f"No students found for project {project_id} in local database.")
        sys.exit(1)

    project = LocalDB.get_project(project_id)
    academic_year = project.get("academic_year", "2026-27") if project else "2026-27"

    # 2. Build mapping of expected filename -> student list
    expected_to_students = {}
    for s in students:
        prev_count = LocalDB.get_photo_count(s["_id"])
        version = prev_count + 1
        expected_fn = get_expected_filename(s, version)
        if expected_fn not in expected_to_students:
            expected_to_students[expected_fn] = []
        expected_to_students[expected_fn].append(s)

    # 3. Scan files recursively
    scanned_files = []
    for root, _, files in os.walk(final_folder):
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                full_path = os.path.join(root, f)
                scanned_files.append((f, full_path))

    # 4. Match
    results = []
    stats = {
        "Total files scanned": len(scanned_files),
        "Exact matches": 0,
        "Already assigned": 0,
        "Ambiguous": 0,
        "Conflicts": 0,
        "Unknown files": 0,
        "Skipped files": 0
    }

    for filename, filepath in scanned_files:
        if filename in expected_to_students:
            matched = expected_to_students[filename]
            if len(matched) == 1:
                student = matched[0]
                status = student.get("photo_status", "not_captured")
                if status == "captured":
                    # Check if this exact file is assigned
                    curr = LocalDB.get_current_photo(student["_id"])
                    if curr and curr.get("final_filename") == filename:
                        stats["Already assigned"] += 1
                        action = "SKIP (Already assigned)"
                    else:
                        stats["Conflicts"] += 1
                        action = "SKIP (Student already captured with different photo)"
                else:
                    stats["Exact matches"] += 1
                    action = "ASSIGN" if not is_dry_run else "WOULD ASSIGN"
                    
                    if not is_dry_run:
                        # Execute assignment
                        std = student.get("standard") or student.get("class_name") or ""
                        div = student.get("division") or student.get("section") or ""
                        div_clean = re.sub(r'(?i)division\s*', '', div).strip() if div else ""
                        class_dir = f"{std}-{div_clean}" if div_clean and std else str(std)
                        relative_path = f"{academic_year}/{class_dir}/{filename}" if class_dir else f"{academic_year}/{filename}"
                        
                        version = LocalDB.get_photo_count(student["_id"]) + 1
                        
                        photo_doc = {
                            "student_id": student["_id"],
                            "original_filename": filename,  # Unknown original
                            "final_filename": filename,
                            "relative_path": relative_path,
                            "storage_type": "local",
                            "version": version,
                            "status": "completed",
                            "captured_at": datetime.now(timezone.utc),
                            "is_current": True
                        }
                        try:
                            LocalDB.assign_photo(student["_id"], photo_doc, str(uuid.uuid4()))
                        except Exception as e:
                            print(f"Failed to assign photo for {student['name']}: {e}")

                results.append({
                    "filename": filename,
                    "matched_student_id": student["_id"],
                    "student_name": student["name"],
                    "GR": student.get("gr", ""),
                    "school_id": student.get("school_id", ""),
                    "project_id": student.get("project_id", ""),
                    "current_photo_status": status,
                    "proposed_photo_status": "captured",
                    "confidence": "HIGH",
                    "reason": "Exact filename match",
                    "action": action
                })
            else:
                stats["Ambiguous"] += 1
                stats["Skipped files"] += 1
                results.append({
                    "filename": filename,
                    "matched_student_id": "",
                    "student_name": "",
                    "GR": "",
                    "school_id": "",
                    "project_id": project_id,
                    "current_photo_status": "",
                    "proposed_photo_status": "",
                    "confidence": "LOW",
                    "reason": f"Ambiguous: {len(matched)} students generate this filename",
                    "action": "SKIP (Ambiguous)"
                })
        else:
            stats["Unknown files"] += 1
            stats["Skipped files"] += 1
            results.append({
                "filename": filename,
                "matched_student_id": "",
                "student_name": "",
                "GR": "",
                "school_id": "",
                "project_id": project_id,
                "current_photo_status": "",
                "proposed_photo_status": "",
                "confidence": "NONE",
                "reason": "Filename does not match any pending student expected names",
                "action": "SKIP (Unknown)"
            })

    # 5. Write Report
    if results:
        keys = results[0].keys()
        with open(report_path, 'w', newline='', encoding='utf-8') as output_file:
            dict_writer = csv.DictWriter(output_file, keys)
            dict_writer.writeheader()
            dict_writer.writerows(results)

    print("=== SUMMARY ===")
    for k, v in stats.items():
        print(f"{k}: {v}")
    print(f"\nReport written to: {report_path}")

if __name__ == "__main__":
    main()
