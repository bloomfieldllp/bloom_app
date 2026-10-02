import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from main import app
from database import get_db

db = get_db()
for idx in db.students.list_indexes():
    print(idx)
