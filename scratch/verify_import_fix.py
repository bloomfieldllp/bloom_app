import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
config.settings.IS_LOCAL_OPERATOR = False

from database import get_db, init_db
from services.student_import_service import StudentImportService

init_db()
db = get_db()

db.schools.delete_many({"name": "Test Replace School", "school_code": "TEST-R"})
school_id = str(db.schools.insert_one({"name": "Test Replace School", "school_code": "TEST-R"}).inserted_id)

db.projects.delete_many({"name": "Replace P1"})
db.projects.delete_many({"name": "Replace P2"})
project_id = str(db.projects.insert_one({"name": "Replace P1", "school_id": school_id}).inserted_id)
other_project_id = str(db.projects.insert_one({"name": "Replace P2", "school_id": school_id}).inserted_id)

db.students.delete_many({"school_id": school_id})
# Old student in current project
db.students.insert_one({
    "school_id": school_id, "project_id": project_id, "gr": "111", "name": "Will Be Wiped"
})
# Conflicting student in another project
db.students.insert_one({
    "school_id": school_id, "project_id": other_project_id, "gr": "222", "name": "From Other Project"
})

valid_records = [
    # A completely new GR
    {"gr": "333", "name": "New GR", "standard": "1", "division": "A", "roll_number": "1", "raw_data": "{}"},
    # The conflicting GR
    {"gr": "222", "name": "Updated From Other Project", "standard": "2", "division": "B", "roll_number": "2", "raw_data": "{}"}
]

print("Executing replace...")
StudentImportService.execute_import(school_id, project_id, valid_records, "replace")
print("Success!")

print("Verifying database state...")
docs = list(db.students.find({"school_id": school_id}))
print(f"Total students in school: {len(docs)}")
for d in docs:
    print(f" - GR: {d.get('gr')}, Name: {d.get('name')}, Project: {'THIS' if d.get('project_id') == project_id else 'OTHER'}")

