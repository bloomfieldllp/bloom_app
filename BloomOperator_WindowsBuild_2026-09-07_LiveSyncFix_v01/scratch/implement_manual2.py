import re
with open("services/student_import_service.py", "r") as f:
    content = f.read()

execute_func = """    @staticmethod
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
                    
        return {"inserted": inserted, "updated": updated}"""

content = re.sub(r'    @staticmethod\n    def manual_execute_import.*', execute_func, content, flags=re.DOTALL)
with open("services/student_import_service.py", "w") as f:
    f.write(content)
