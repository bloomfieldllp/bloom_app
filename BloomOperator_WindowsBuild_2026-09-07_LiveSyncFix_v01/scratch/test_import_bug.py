import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
config.settings.IS_LOCAL_OPERATOR = False

from database import get_db, init_db
from services.student_import_service import StudentImportService
from bson import ObjectId

# Ensure indexes
init_db()
db = get_db()

# Create dummy school and project
db.schools.delete_many({"name": "Import Test School"})
school_id = str(db.schools.insert_one({"name": "Import Test School"}).inserted_id)

db.projects.delete_many({"name": "Import Test Project"})
project_id = str(db.projects.insert_one({"name": "Import Test Project", "school_id": school_id}).inserted_id)

db.projects.delete_many({"name": "Other Project"})
other_project_id = str(db.projects.insert_one({"name": "Other Project", "school_id": school_id}).inserted_id)

db.students.delete_many({"school_id": school_id})

# Let's say another project in the same school has GR=123
db.students.insert_one({
    "school_id": school_id,
    "project_id": other_project_id,
    "gr": "123",
    "name": "Existing Student",
    "photo_status": "Pending"
})

# Now we import into project_id with action='replace' and GR=123
valid_records = [
    {"gr": "123", "name": "New Student", "photo_status": "Pending", "standard": "10", "division": "A", "roll_number": "1", "raw_data": "{}"}
]

try:
    print("Executing replace...")
    StudentImportService.execute_import(school_id, project_id, valid_records, "replace")
    print("Success!")
except Exception as e:
    import traceback
    traceback.print_exc()

