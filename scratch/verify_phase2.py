import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from main import app
from fastapi.testclient import TestClient

test_client = TestClient(app)

# The app automatically initializes DB connection and indexes when app starts 
# (which happened when we imported app and instantiated TestClient).
from database import get_db
db = get_db()

def get_session(phone, password):
    res = test_client.post("/login", data={"username": phone, "password": password}, follow_redirects=False)
    assert res.status_code == 303, f"Login failed for {phone}. Status: {res.status_code}"
    return res.cookies

def run_verifications():
    print("--- 1. TEST DATA CLEANUP ---")
    test_student = db.students.find_one({"gr": "TEST-162747"})
    if not test_student:
        test_student = db.students.find_one({"name": "Phase 2 Test Student"})
    
    if test_student:
        print(f"Found test student: {test_student['_id']}, GR: {test_student['gr']}")
        res = db.students.delete_one({"_id": test_student["_id"]})
        print(f"Deleted {res.deleted_count} test student(s).")
    else:
        print("Test student not found. Already cleaned up?")

    print("\n--- 2. MONGODB INDEX VERIFICATION ---")
    indexes = list(db.students.list_indexes())
    school_gr_index_found = False
    project_gr_index_found = False
    
    for idx in indexes:
        keys = list(idx["key"].keys())
        if keys == ["school_id", "gr"]:
            school_gr_index_found = True
            print(f"Found required index: {idx['name']} -> {idx['key']} (unique: {idx.get('unique')})")
        if keys == ["project_id", "gr"]:
            project_gr_index_found = True
            print(f"Found INCORRECT index: {idx['name']} -> {idx['key']}")
            
    if school_gr_index_found and not project_gr_index_found:
        print("PASS: Indexes are correct.")
    else:
        print("FAIL: Index verification failed.")

    print("\n--- 3. EXISTING DATA SAFETY ---")
    mock_project = db.projects.find_one({"_id": "60d5ec34b0d87a4190c7bfa4"})
    if mock_project:
        print("FAIL: Mock project was reintroduced!")
    else:
        print("PASS: No mock project found.")
        
    print("\n--- 4. GR IMMUTABILITY & SAME GR ACROSS SCHOOLS & RBAC ---")
    admin_cookies = get_session("9426407970", "Swami@2003")
    
    from services.student_service import StudentService
    
    schools = list(db.schools.find().limit(2))
    if len(schools) < 2:
        print("Not enough schools to test cross-school logic.")
        return
        
    s1 = schools[0]
    s2 = schools[1]
    
    p1 = db.projects.find_one({"school_id": str(s1["_id"])})
    p2 = db.projects.find_one({"school_id": str(s2["_id"])})
    
    if p1 and p2:
        gr_val = "SHARED_GR_123"
        db.students.delete_many({"gr": gr_val})
        
        try:
            id1 = StudentService.create_student(str(s1["_id"]), str(p1["_id"]), gr_val, "Test S1")
            id2 = StudentService.create_student(str(s2["_id"]), str(p2["_id"]), gr_val, "Test S2")
            print("PASS: Same GR created across different schools.")
        except Exception as e:
            print(f"FAIL: Same GR failed: {e}")
            
        try:
            StudentService.update_student(id1, name="New Name", standard="10")
            student = StudentService.get_student(id1)
            if student["gr"] == gr_val and student["name"] == "New Name":
                print("PASS: update_student modifies other fields, GR remains immutable by signature/logic.")
            else:
                print("FAIL: GR changed or name didn't update!")
        except Exception as e:
            print(f"FAIL: update_student error: {e}")
            
        op1 = db.users.find_one({"role": "bloom_operator"})
        if op1:
            p_op = db.projects.find_one({"assigned_operator_id": str(op1["_id"])})
            if p_op:
                op_school = p_op["school_id"]
                target_student = db.students.find_one({"school_id": {"$ne": op_school}})
                if target_student:
                    # Test HTTP edit via operator to a student in a different project/school
                    op_cookies = get_session(op1["phone"], "password123")
                    res = test_client.post(
                        f"/operator/projects/{p_op['_id']}/students/edit",
                        data={"student_id": str(target_student["_id"]), "name": "Hacked Name"},
                        cookies=op_cookies,
                        follow_redirects=False
                    )
                    if res.status_code == 403:
                        print("PASS: Cross-school edit rejected via HTTP 403.")
                    else:
                        print(f"FAIL: Cross-school edit returned {res.status_code}")
        
        db.students.delete_many({"gr": gr_val})
        
if __name__ == "__main__":
    run_verifications()
