import asyncio
from fastapi import Request
from fastapi.datastructures import Headers
from fastapi import UploadFile
import io

from routes.school import import_preview

async def main():
    class MockRequest(Request):
        def __init__(self):
            self._headers = Headers({"host": "localhost"})
            self.scope = {"type": "http", "headers": self._headers.raw, "client": ("127.0.0.1", 8000)}
            
    req = MockRequest()
    
    file_content = b"GR,Name,Standard,Division,Roll Number\n1,Alice,1,A,1\n"
    file = UploadFile(filename="test.csv", file=io.BytesIO(file_content))
    
    user = {"school_id": "60d5ec34b0d87a4190c7bfa3"}
    
    try:
        res = await import_preview(req, "6a96a757962ba17e81ea4435", [file], user)
        print("Success:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(main())
