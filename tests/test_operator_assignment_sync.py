import pytest
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from unittest.mock import patch
from routes.sync import api_pull, PullRequest
import asyncio

class MockDB:
    def __init__(self):
        import mongomock
        self.client = mongomock.MongoClient('localhost', 27017)
        self.db = self.client.bloom_test
        
    @property
    def schools(self): return self.db.schools
    @property
    def projects(self): return self.db.projects
    @property
    def students(self): return self.db.students
    @property
    def student_photos(self): return self.db.student_photos

@pytest.fixture
def mock_db_instance():
    return MockDB()

def test_operator_assignment_sync(mock_db_instance):
    async def run_test():
        db = mock_db_instance
        
        # Setup School
        school_id = ObjectId()
        db.schools.insert_one({
            "_id": school_id,
            "name": "Test School",
            "updated_at": datetime.now(timezone.utc) - timedelta(days=2)
        })
        
        # Setup Project
        project_id = ObjectId()
        db.projects.insert_one({
            "_id": project_id,
            "school_id": str(school_id),
            "assigned_operator_id": "9574077210",
            "updated_at": datetime.now(timezone.utc) # Updated recently (assigned operator)
        })
        
        # Setup Students (created 2 days ago, NOT recently updated)
        for i in range(386):
            db.students.insert_one({
                "school_id": str(school_id),
                "project_id": str(project_id),
                "gr": str(i),
                "name": f"Student {i}",
                "photo_status": "not_captured",
                "updated_at": datetime.now(timezone.utc) - timedelta(days=2)
            })
            
        with patch("routes.sync.get_db", return_value=db):
            req = PullRequest(operator_id="9574077210", since_version=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat())
            res = await api_pull(req)
            
            # Verify operator gets the project
            assert len(res["projects"]) == 1
            
            # Verify operator gets ALL students because the project was updated!
            assert len(res["students"]) == 386

    asyncio.run(run_test())

if __name__ == "__main__":
    pytest.main(["-v", "tests/test_operator_assignment_sync.py"])
