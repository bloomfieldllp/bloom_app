import pymongo
from pymongo import MongoClient
import mongomock
from bson import ObjectId
from datetime import datetime, timezone
import logging
from config import settings

logger = logging.getLogger("app.database")

# Global client and db placeholders
client = None
db = None
is_mock = False

def get_db():
    global client, db, is_mock
    if db is None:
        logger.info("Attempting to connect to real MongoDB instance...")
        # Increase timeout to 5 seconds to accommodate Vercel cold starts
        client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000, socketTimeoutMS=5000)
        # Trigger a ping check to fail fast if connection cannot be established
        client.admin.command("ping")
        db = client[settings.MONGODB_DATABASE]
        is_mock = False
        logger.info("Successfully connected to real MongoDB instance.")
    return db

def seed_mock_data(database):
    import bcrypt
    
    def hash_pwd(pwd):
        return bcrypt.hashpw(pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Seed Admin User
    admin_phone = "9426407970"
    admin_email = "bloomgrapheteria@gmail.com"
    if not database.users.find_one({"phone": admin_phone}):
        database.users.insert_one({
            "_id": ObjectId("60d5ec34b0d87a4190c7bfa0"),
            "name": "Bloom Admin",
            "email": admin_email,
            "phone": admin_phone,
            "role": "bloom_admin",
            "school_id": None,
            "status": "active",
            "password_hash": hash_pwd("Swami@2003"),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        })

    # Seed School
    school_id = ObjectId("60d5ec34b0d87a4190c7bfa1")
    if not database.schools.find_one({"_id": school_id}):
        database.schools.insert_one({
            "_id": school_id,
            "name": "Springfield Academy",
            "school_code": "SFA123",
            "hm": {
                "name": "John Doe",
                "phone": "1234567890",
                "user_id": "60d5ec34b0d87a4190c7bfa2"
            },
            "school_email": "school@bloom.com",
            "location_link": "https://maps.google.com",
            "status": "active",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        })

    # Seed School Admin User
    school_admin_phone = "1234567890"
    if not database.users.find_one({"phone": school_admin_phone}):
        database.users.insert_one({
            "_id": ObjectId("60d5ec34b0d87a4190c7bfa2"),
            "name": "John Doe",
            "email": "school@bloom.com",
            "phone": school_admin_phone,
            "role": "school_admin",
            "school_id": str(school_id),
            "status": "active",
            "password_hash": hash_pwd("password123"),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        })

    # Seed Operator User
    operator_phone = "9876543210"
    if not database.users.find_one({"phone": operator_phone}):
        database.users.insert_one({
            "_id": ObjectId("60d5ec34b0d87a4190c7bfa3"),
            "name": "Jane Operator",
            "email": "operator@bloom.com",
            "phone": operator_phone,
            "role": "bloom_operator",
            "school_id": None,
            "status": "active",
            "password_hash": hash_pwd("password123"),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        })

    # Seed Project
    project_id = ObjectId("60d5ec34b0d87a4190c7bfa4")
    if not database.projects.find_one({"_id": project_id}):
        database.projects.insert_one({
            "_id": project_id,
            "project_id": "PRJ_2026_00001",
            "school_id": str(school_id),
            "name": "Springfield Academy - 2026-27",
            "academic_year": "2026-27",
            "photography_start_date": datetime(2026, 9, 1, tzinfo=timezone.utc),
            "assigned_operator_id": "60d5ec34b0d87a4190c7bfa3",
            "status": "scheduled",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        })

    # Seed Students
    student1_gr = "1001"
    if not database.students.find_one({"gr": student1_gr}):
        database.students.insert_one({
            "_id": ObjectId("60d5ec34b0d87a4190c7bfa5"),
            "name": "Alice Smith",
            "gr": student1_gr,
            "class_name": "Grade 5",
            "section": "A",
            "school_id": str(school_id),
            "project_id": str(project_id),
            "photo_status": "captured",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        })

    student2_gr = "1002"
    if not database.students.find_one({"gr": student2_gr}):
        database.students.insert_one({
            "_id": ObjectId("60d5ec34b0d87a4190c7bfa6"),
            "name": "Bob Jones",
            "gr": student2_gr,
            "class_name": "Grade 5",
            "section": "B",
            "school_id": str(school_id),
            "project_id": str(project_id),
            "photo_status": "pending",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        })
    logger.info("Successfully seeded mock data inside memory database.")

def init_db():
    if settings.IS_LOCAL_OPERATOR:
        try:
            from services.local_db import LocalDB
            LocalDB.init_db()
        except Exception as e:
            logger.error(f"Failed to initialize local SQLite database: {e}")
        return
            
    try:
        database = get_db()

        
        # Create indexes
        database.schools.create_index("school_code", unique=True)
        
        try:
            database.users.update_many({"email": None}, {"$unset": {"email": ""}})
        except Exception:
            pass
        try:
            database.users.drop_index("email_1")
        except Exception:
            pass
            
        database.users.create_index("email", unique=True, sparse=True)
        database.users.create_index("phone", unique=True)
        database.users.create_index("school_id")
        
        database.projects.create_index([("school_id", 1), ("academic_year", 1)])
        
        try:
            database.students.drop_index("project_id_1_gr_1")
        except Exception:
            pass
            
        database.students.create_index([("school_id", 1), ("gr", 1)], unique=True)
        database.students.create_index("school_id")
        database.students.create_index("name")
        database.students.create_index("gr")
        database.students.create_index("photo_status")

        # Automatically create default super-admin if not present in real DB
        default_email = "bloomgrapheteria@gmail.com"
        default_phone = "9426407970"
        if not database.users.find_one({"$or": [{"email": default_email}, {"phone": default_phone}]}):
            import bcrypt
            database.users.insert_one({
                "_id": ObjectId("60d5ec34b0d87a4190c7bfa0"),
                "name": "Bloom Admin",
                "email": default_email,
                "phone": default_phone,
                "role": "bloom_admin",
                "school_id": None,
                "status": "active",
                "password_hash": bcrypt.hashpw("Swami@2003".encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            })
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"MONGODB CONNECTION ERROR: {e}")
        logger.error("Could not connect to MongoDB Atlas cluster.")
        logger.error("The application will continue starting with memory-mocked db.")
        logger.error("=" * 60)

def close_db():
    global client, db
    if client is not None:
        try:
            client.close()
        except Exception:
            pass
        client = None
        db = None
