import sys
import os
import json
import uuid

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient
from main import app
from database import get_db

client = TestClient(app)
db = get_db()

def run_tests():
    print("--- WEB PORTAL REGRESSION ---")
    res = client.post("/login", data={"username": "9426407970", "password": "Swami@2003"}, follow_redirects=False)
    assert res.status_code == 303
    cookies = res.cookies
    
    res = client.get("/admin", cookies=cookies)
    assert res.status_code == 200
    print("Admin dashboard loads.")
    
    # Check operator dashboard
    op = db.users.find_one({"role": "bloom_operator"})
    res = client.post("/login", data={"username": op["phone"], "password": "password123"}, follow_redirects=False)
    op_cookies = res.cookies
    res = client.get("/operator", cookies=op_cookies)
    assert res.status_code == 200
    print("Operator dashboard loads.")
    
    # Check operator session
    project = db.projects.find_one({"assigned_operator_id": str(op["_id"])})
    if project:
        res = client.get(f"/operator/projects/{project['_id']}/session", cookies=op_cookies)
        assert res.status_code == 200
        print("Operator session loads.")
        
        # Check settings
        res = client.get(f"/operator/projects/{project['_id']}/settings", cookies=op_cookies)
        assert res.status_code == 200
        print("Operator settings loads.")
        
    print("--- OFFLINE / ONLINE REGRESSION ---")
    # Test sync snapshot endpoint
    res = client.post("/api/sync/snapshot", cookies=op_cookies)
    assert res.status_code == 200
    print("Snapshot sync endpoint works.")
    
    print("--- DATA INTEGRITY ---")
    mock_project = db.projects.find_one({"_id": "60d5ec34b0d87a4190c7bfa4"})
    assert mock_project is None
    print("No mock project found.")
    
run_tests()
