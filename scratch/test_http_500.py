import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
config.settings.IS_LOCAL_OPERATOR = False
from fastapi.testclient import TestClient
from main import app
from database import get_db, init_db
import json
from bson import ObjectId
import datetime

client = TestClient(app)
init_db()
db = get_db()

# Prepare mock data
db.users.delete_many({"phone": "testadmin"})
school_id = str(db.schools.insert_one({"name": "Test School HTTP"}).inserted_id)
user_id = str(db.users.insert_one({
    "phone": "testadmin", "password_hash": "hash", "role": "school_admin", "school_id": school_id
}).inserted_id)

project_id = str(db.projects.insert_one({"name": "P1", "school_id": school_id}).inserted_id)
other_project_id = str(db.projects.insert_one({"name": "P2", "school_id": school_id}).inserted_id)

# Insert conflicting student in another project
db.students.insert_one({
    "school_id": school_id,
    "project_id": other_project_id,
    "gr": "HTTP-123",
    "name": "Old Name",
    "photo_status": "Pending"
})

# Fake temp file
temp_file_id = db.temp_files.insert_one({
    "file_bytes": b"GR,Name,Std\nHTTP-123,New Name,10\n",
    "created_at": datetime.datetime.now()
}).inserted_id

mapping = {"gr_col": "GR", "name_col": "Name", "std_col": "Std"}

print(f"Trying to hit /school/projects/{project_id}/execute-import")
res = client.post("/login", data={"username": "testadmin", "password": "password123"}, follow_redirects=False)
# Mock authentication manually by just giving a token or bypassing
# Wait, I'll use the actual app auth, but I didn't set password correctly.
# I will just write a function to simulate the execute_import handler
