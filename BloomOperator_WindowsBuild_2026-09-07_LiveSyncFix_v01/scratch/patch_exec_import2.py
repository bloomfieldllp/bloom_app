with open("services/student_import_service.py", "r") as f:
    lines = f.readlines()

out = []
in_func = False
for line in lines:
    if "def manual_execute_import(" in line:
        in_func = True
        out.append(line)
        # Append our new logic
        out.append("""        from datetime import datetime, timezone
        db = get_db()
        now = datetime.now(timezone.utc)
        
        inserted = 0
        updated = 0
        deleted = 0
        
        if action == "replace":
            del_res = db.students.delete_many({"project_id": project_id})
            deleted = del_res.deleted_count
            for rec in valid_records:
                gr = rec["gr"]
                existing = db.students.find_one({"school_id": school_id, "gr": gr})
                
                doc = {
                    "name": rec["name"],
                    "standard": rec.get("standard", ""),
                    "division": rec.get("division", ""),
                    "section": rec.get("section", ""),
                    "roll_number": rec.get("roll_number", ""),
                    "date_of_birth": rec.get("date_of_birth", ""),
                    "address": rec.get("address", ""),
                    "contact": rec.get("contact", ""),
                    "gender": rec.get("gender", ""),
                    "project_id": project_id,
                    "updated_at": now
                }
                if "custom_fields" in rec:
                    doc["custom_fields"] = rec["custom_fields"]
                    
                if existing:
                    db.students.update_one({"_id": existing["_id"]}, {"$set": doc})
                    inserted += 1 
                else:
                    doc["school_id"] = school_id
                    doc["gr"] = gr
                    doc["created_at"] = now
                    doc["photo_status"] = "not_captured"
                    db.students.insert_one(doc)
                    inserted += 1
                    
        elif action == "update":
            for rec in valid_records:
                gr = rec["gr"]
                existing = db.students.find_one({"school_id": school_id, "gr": gr})
                
                doc = {
                    "name": rec["name"],
                    "standard": rec.get("standard", ""),
                    "division": rec.get("division", ""),
                    "section": rec.get("section", ""),
                    "roll_number": rec.get("roll_number", ""),
                    "date_of_birth": rec.get("date_of_birth", ""),
                    "address": rec.get("address", ""),
                    "contact": rec.get("contact", ""),
                    "gender": rec.get("gender", ""),
                    "project_id": project_id,
                    "updated_at": now
                }
                if "custom_fields" in rec:
                    doc["custom_fields"] = rec["custom_fields"]
                    
                if existing:
                    db.students.update_one({"_id": existing["_id"]}, {"$set": doc})
                    updated += 1
                else:
                    doc["school_id"] = school_id
                    doc["gr"] = gr
                    doc["created_at"] = now
                    doc["photo_status"] = "not_captured"
                    db.students.insert_one(doc)
                    inserted += 1
                    
        elif action == "add_only":
            existing_students = list(db.students.find({"school_id": school_id}, {"gr": 1}))
            existing_grs = {s["gr"] for s in existing_students if s.get("gr")}
            
            for rec in valid_records:
                gr = rec["gr"]
                if gr not in existing_grs:
                    doc = {
                        "school_id": school_id,
                        "project_id": project_id,
                        "gr": gr,
                        "name": rec["name"],
                        "standard": rec.get("standard", ""),
                        "division": rec.get("division", ""),
                        "section": rec.get("section", ""),
                        "roll_number": rec.get("roll_number", ""),
                        "date_of_birth": rec.get("date_of_birth", ""),
                        "address": rec.get("address", ""),
                        "contact": rec.get("contact", ""),
                        "gender": rec.get("gender", ""),
                        "created_at": now,
                        "updated_at": now,
                        "photo_status": "not_captured"
                    }
                    if "custom_fields" in rec:
                        doc["custom_fields"] = rec["custom_fields"]
                    db.students.insert_one(doc)
                    inserted += 1
                    
        return {"inserted": inserted, "updated": updated, "deleted": deleted}\n""")
        continue
        
    if in_func:
        if line.strip() == "" or line.startswith("        ") or line.startswith("    @staticmethod"):
            # If it's another method, we're done
            if line.startswith("    @staticmethod"):
                in_func = False
                out.append(line)
        else:
            in_func = False
            out.append(line)
    else:
        out.append(line)

with open("services/student_import_service.py", "w") as f:
    f.writelines(out)
