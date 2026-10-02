import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app
import uuid

client = TestClient(app)

def get_session(phone, password):
    res = client.post("/login", data={"username": phone, "password": password}, follow_redirects=False)
    assert res.status_code == 303
    return res.cookies

def test_add_student():
    cookies = get_session("9426407970", "Swami@2003")
    
    # 1. Fetch project ID
    res = client.get("/admin/projects/directory", cookies=cookies)
    import re
    m = re.search(r'/admin/projects/([0-9a-f]{24})/edit', res.text)
    if not m:
        print("No project found.")
        return
    project_id = m.group(1)
    print("Project ID:", project_id)
    
    # 2. Add student
    gr = f"TEST-{uuid.uuid4().hex[:6]}"
    res = client.post(
        f"/admin/projects/{project_id}/students/add",
        data={
            "gr": gr,
            "name": "Phase 2 Test Student",
            "standard": "10",
            "division": "A",
            "roll_number": "1"
        },
        cookies=cookies,
        follow_redirects=False
    )
    
    print("Add Student Status:", res.status_code)
    print("Add Student Redirect:", res.headers.get("Location"))
    assert res.status_code == 303
    assert "msg=" in res.headers.get("Location")
    
    # 3. Add duplicate student
    res = client.post(
        f"/admin/projects/{project_id}/students/add",
        data={
            "gr": gr,
            "name": "Duplicate Student",
            "standard": "10"
        },
        cookies=cookies,
        follow_redirects=False
    )
    print("Add Duplicate Status:", res.status_code)
    print("Add Duplicate Redirect:", res.headers.get("Location"))
    assert res.status_code == 303
    assert "error=" in res.headers.get("Location")
    print("PASS: Duplicate rejected.")

if __name__ == "__main__":
    test_add_student()
