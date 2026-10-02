import asyncio
from fastapi import Request
from fastapi.datastructures import Headers
import unittest.mock as mock

mock_db = mock.MagicMock()
def mock_get_db():
    return mock_db

import database
database.get_db = mock_get_db

from routes.school import execute_import

async def main():
    class MockRequest(Request):
        def __init__(self):
            self._headers = Headers({"host": "localhost"})
            self.scope = {"type": "http", "headers": self._headers.raw, "client": ("127.0.0.1", 8000)}
            
    req = MockRequest()
    
    mock_db.projects.find_one.return_value = {"_id": "6a96a757962ba17e81ea4435", "school_id": "60d5ec34b0d87a4190c7bfa3"}
    mock_db.temp_files.find_one.return_value = {"valid_records": [], "new_custom_fields": {}}
    
    user = {"school_id": "60d5ec34b0d87a4190c7bfa3"}
    
    try:
        res = await execute_import(req, "6a96a757962ba17e81ea4435", "temp_id", "filename.csv", "update", user)
        print("Success:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(main())
