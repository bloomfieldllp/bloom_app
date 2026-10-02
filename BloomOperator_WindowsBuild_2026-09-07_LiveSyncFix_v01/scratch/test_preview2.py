import asyncio
from fastapi import Request
from fastapi.datastructures import Headers
from fastapi import UploadFile
import io
import unittest.mock as mock

# Mock get_db
mock_db = mock.MagicMock()
def mock_get_db():
    return mock_db

import database
database.get_db = mock_get_db

from routes.school import import_preview

async def main():
    class MockRequest(Request):
        def __init__(self):
            self._headers = Headers({"host": "localhost"})
            self.scope = {"type": "http", "headers": self._headers.raw, "client": ("127.0.0.1", 8000)}
            
    req = MockRequest()
    
    file_content = b"GR,Name,Standard,Division,Roll Number\n1,Alice,1,A,1\n"
    file = UploadFile(filename="test.csv", file=io.BytesIO(file_content))
    
    mock_db.projects.find_one.return_value = {"_id": "6a96a757962ba17e81ea4435", "school_id": "60d5ec34b0d87a4190c7bfa3"}
    mock_db.schools.find_one.return_value = {"_id": "60d5ec34b0d87a4190c7bfa3", "custom_fields": []}
    mock_db.temp_files.insert_one.return_value.inserted_id = "mocked_temp_id"
    
    user = {"school_id": "60d5ec34b0d87a4190c7bfa3", "role": "school_admin", "name": "Admin", "email": "test@test.com"}
    
    try:
        res = await import_preview(req, "6a96a757962ba17e81ea4435", [file], user)
        print("Success:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(main())
