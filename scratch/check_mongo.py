import sys
import os
sys.path.insert(0, os.path.abspath('.'))
from database import get_db

db = get_db()
indexes = list(db.students.index_information().items())
print("Indexes on students collection:")
for name, info in indexes:
    print(f"- {name}: {info}")

pipeline = [
    {"$group": {"_id": {"school_id": "$school_id", "gr": "$gr"}, "count": {"$sum": 1}}},
    {"$match": {"count": {"$gt": 1}}}
]
duplicates = list(db.students.aggregate(pipeline))
print(f"\nDuplicates by school_id, gr: {len(duplicates)}")
for doc in duplicates:
    print(doc)
