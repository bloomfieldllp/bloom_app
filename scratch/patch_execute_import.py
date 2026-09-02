import re

with open("services/student_import_service.py", "r") as f:
    content = f.read()
    
# We need to rewrite execute_import to handle custom_fields and date_of_birth etc, and register school fields.
# Actually I'll append another method: `intelligent_execute_import` and call that instead from routes.

methods = """
    @staticmethod
    def intelligent_execute_import(
        school_id: str,
        project_id: str,
        valid_records: List[Dict[str, Any]],
        action: str,
        new_custom_fields: Dict[str, str] = None
    ) -> Dict[str, int]:
        db = get_db()
        now = datetime.now(timezone.utc)
        
        # 1. Update school schema if new fields
        if new_custom_fields:
            try:
                from bson import ObjectId
                school = db.schools.find_one({"_id": ObjectId(school_id)})
                if school:
                    existing = school.get("custom_fields", [])
                    existing_keys = {f["key"] for f in existing}
                    
                    for k, label in new_custom_fields.items():
                        if k not in existing_keys:
                            existing.append({
                                "key": k,
                                "label": label,
                                "type": "text",
                                "active": True,
                                "order": len(existing) + 1
                            })
                    
                    db.schools.update_one(
                        {"_id": ObjectId(school_id)},
                        {"$set": {"custom_fields": existing}}
                    )
            except Exception:
                pass
                
        inserted_count = 0
        updated_count = 0
        deleted_count = 0
        
        if action == "replace":
            del_result = db.students.delete_many({"project_id": project_id})
            deleted_count = del_result.deleted_count
            
            for r in valid_records:
                gr_val = r["gr"]
                existing = db.students.find_one({"school_id": school_id, "gr": gr_val})
                if existing:
                    db.students.update_one(
                        {"_id": existing["_id"]},
                        {
                            "$set": {
                                "name": r["name"],
                                "standard": r["standard"],
                                "roll_number": r["roll_number"],
                                "division": r["division"],
                                "date_of_birth": r.get("date_of_birth", ""),
                                "address": r.get("address", ""),
                                "custom_fields": r.get("custom_fields", {}),
                                "raw_data": r.get("raw_data", {}),
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
                    r["photo_status"] = "not_captured"
                    db.students.insert_one(r)
                    inserted_count += 1
                    
        elif action == "update":
            for r in valid_records:
                gr_val = r["gr"]
                existing = db.students.find_one({"school_id": school_id, "gr": gr_val})
                if existing:
                    db.students.update_one(
                        {"_id": existing["_id"]},
                        {
                            "$set": {
                                "name": r["name"],
                                "standard": r["standard"],
                                "roll_number": r["roll_number"],
                                "division": r["division"],
                                "date_of_birth": r.get("date_of_birth", ""),
                                "address": r.get("address", ""),
                                "custom_fields": r.get("custom_fields", {}),
                                "raw_data": r.get("raw_data", {}),
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
                    r["photo_status"] = "not_captured"
                    db.students.insert_one(r)
                    inserted_count += 1
                    
        elif action == "add_only":
            existing_students = list(db.students.find({"school_id": school_id}, {"gr": 1}))
            existing_grs = {s["gr"] for s in existing_students}
            
            records_to_insert = []
            for r in valid_records:
                if r["gr"] not in existing_grs:
                    r["school_id"] = school_id
                    r["project_id"] = project_id
                    r["created_at"] = now
                    r["updated_at"] = now
                    r["photo_status"] = "not_captured"
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
"""
with open("services/student_import_service.py", "a") as f:
    f.write(methods)
