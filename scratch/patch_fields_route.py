import re

route_code = """
@router.get("/schools/{school_id}/fields")
async def get_school_fields(request: Request, school_id: str, user = Depends(RoleChecker([{roles}]))):
    from database import get_db
    db = get_db()
    try:
        from bson import ObjectId
        school = db.schools.find_one({"_id": ObjectId(school_id)})
        if school and "custom_fields" in school:
            return school["custom_fields"]
    except Exception:
        pass
        
    # If offline, get from local SQLite
    if getattr(request.app.state, "is_local_operator", False) or True: # fallback
        try:
            from services.local_db import LocalDB
            conn = LocalDB.get_connection()
            row = conn.execute("SELECT custom_fields FROM schools WHERE id = ?", (school_id,)).fetchone()
            if row and row[0]:
                import json
                return json.loads(row[0])
        except Exception:
            pass
            
    return []

"""

# Admin
with open("routes/admin.py", "r") as f:
    admin_code = f.read()
admin_code += route_code.replace("{roles}", '"bloom_admin"')
with open("routes/admin.py", "w") as f:
    f.write(admin_code)

# Operator
with open("routes/operator.py", "r") as f:
    operator_code = f.read()
operator_code += route_code.replace("{roles}", '"bloom_operator"')
with open("routes/operator.py", "w") as f:
    f.write(operator_code)

# School
with open("routes/school.py", "r") as f:
    school_code = f.read()
school_code += route_code.replace("{roles}", '"school_admin"')
with open("routes/school.py", "w") as f:
    f.write(school_code)

