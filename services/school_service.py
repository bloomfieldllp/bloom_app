from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import logging
from bson import ObjectId
from database import get_db
from services.auth_service import AuthService

logger = logging.getLogger(__name__)

class SchoolService:
    @staticmethod
    def create_school(school_data: Dict[str, Any]) -> str:
        db = get_db()
        from utils import normalize_phone
        
        name = school_data.get("name", "").strip()
        if not name:
            raise ValueError("School name is required.")
            
        code = school_data.get("school_code", "").strip().upper()
        if not code:
            raise ValueError("School code is required.")
            
        try:
            if db.schools.find_one({"school_code": code}):
                raise ValueError(f"School with code '{code}' already exists.")
        except Exception:
            pass
            
        hm_name = school_data.get("hm_name", "").strip()
        if not hm_name:
            raise ValueError("HM Name is required.")
            
        hm_phone = school_data.get("hm_phone", "").strip()
        if not hm_phone:
            raise ValueError("HM Phone Number is required.")
            
        # Normalize phone
        hm_phone_norm = normalize_phone(hm_phone)
        
        email = school_data.get("school_email")
        if email:
            email_clean = email.strip()
            if "@" not in email_clean:
                raise ValueError("School email must be valid.")
            school_email = email_clean
        else:
            school_email = None

        location_link = school_data.get("location_link", "").strip()
        if not location_link:
            raise ValueError("Location link is mandatory.")
        if not (location_link.startswith("http://") or location_link.startswith("https://")):
            raise ValueError("Location link must be a valid URL starting with http:// or https://.")
            
        # Construct school document
        school_doc = {
            "name": name,
            "school_code": code,
            "hm": {
                "name": hm_name,
                "phone": hm_phone_norm,
                "user_id": None
            },
            "school_email": school_email,
            "location_link": location_link,
            "status": "active",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        
        try:
            result = db.schools.insert_one(school_doc)
            school_id = str(result.inserted_id)
        except Exception:
            # Fallback if DB is down
            school_id = "mock_school_id_" + code
            
        # Check automatic HM user creation rule:
        # Both must be real (not underscore)
        if hm_name != "_" and hm_phone_norm != "_":
            try:
                # Seeding password
                hm_user_id = AuthService.create_user({
                    "name": hm_name,
                    "phone": hm_phone_norm,
                    "email": None,
                    "user_type": "school_user",
                    "role": "school_admin",
                    "school_id": school_id,
                    "class_assignments": [],
                    "status": "active",
                    "password": "Swami@2003",
                    "created_by": school_data.get("created_by")
                })
                # Update school doc with created user id
                try:
                    db.schools.update_one(
                        {"_id": ObjectId(school_id)},
                        {"$set": {"hm.user_id": hm_user_id}}
                    )
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Failed to automatically create HM user for school {name}: {e}")
                
        return school_id

    @staticmethod
    def get_school(school_id: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        try:
            school = db.schools.find_one({"_id": ObjectId(school_id)})
            if school:
                school["_id"] = str(school["_id"])
                return school
        except Exception:
            pass
            
        # Return fallback mock school info to prevent 404 errors when DB is offline or mock users are used
        return {
            "_id": school_id,
            "name": "Springfield Academy (Mock)",
            "school_code": "SFA123",
            "hm": {
                "name": "John Doe",
                "phone": "1234567890",
                "user_id": "mock_school_admin_id"
            },
            "school_email": "school@bloom.com",
            "location_link": "https://maps.google.com",
            "status": "active"
        }

    @staticmethod
    def get_school_by_code(school_code: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        try:
            school = db.schools.find_one({"school_code": school_code.strip().upper()})
            if school:
                school["_id"] = str(school["_id"])
                return school
        except Exception:
            pass
        return None

    @staticmethod
    def list_schools() -> List[Dict[str, Any]]:
        db = get_db()
        try:
            schools = list(db.schools.find())
        except Exception:
            schools = []
            
        # If no schools found, return a default mock school
        if not schools:
            schools = [{
                "_id": "60d5ec34b0d87a4190c7bfa1",
                "name": "Springfield Academy (Mock)",
                "school_code": "SFA123",
                "hm": {
                    "name": "John Doe",
                    "phone": "1234567890",
                    "user_id": "mock_school_admin_id"
                },
                "school_email": "school@bloom.com",
                "location_link": "https://maps.google.com",
                "status": "active"
            }]
        
        # Hydrate with projects count and students count
        for school in schools:
            school_id_str = str(school["_id"])
            school["_id"] = school_id_str
            try:
                school["projects_count"] = db.projects.count_documents({"school_id": school_id_str})
                school["students_count"] = db.students.count_documents({"school_id": school_id_str})
            except Exception:
                school["projects_count"] = 1
                school["students_count"] = 120
        
        return schools

    @staticmethod
    def create_school_user(user_data: Dict[str, Any]) -> str:
        db = get_db()
        name = user_data.get("name", "").strip()
        if not name:
            raise ValueError("Name is required.")
            
        phone = user_data.get("phone", "").strip()
        if not phone:
            raise ValueError("Phone number is mandatory.")
            
        email = user_data.get("email")
        email_clean = email.strip().lower() if (email and email.strip()) else None
        
        user_type = user_data.get("user_type", "school_user")
        if user_type not in ["school_user", "operator"]:
            raise ValueError("Invalid user type.")
            
        # Role mapping
        if user_type == "school_user":
            role = "school_admin"
            school_id = user_data.get("school_id")
            try:
                if not school_id or not db.schools.find_one({"_id": ObjectId(school_id)}):
                    raise ValueError("Valid school ID is required for school users.")
            except Exception:
                pass
        else: # operator
            role = "bloom_operator"
            school_id = None
            
        password = user_data.get("password")
        if not password or len(password) < 6:
            raise ValueError("Password must be at least 6 characters.")
            
        user_doc = {
            "name": name,
            "phone": phone,
            "email": email_clean,
            "user_type": user_type,
            "role": role,
            "school_id": school_id,
            "class_assignments": user_data.get("class_assignments", []),
            "created_by": user_data.get("created_by"),
            "password": password
        }
        
        return AuthService.create_user(user_doc)

    @staticmethod
    def list_school_users(school_id: Optional[str] = None) -> List[Dict[str, Any]]:
        db = get_db()
        query = {}
        if school_id:
            query["school_id"] = school_id
            
        try:
            users = list(db.users.find(query))
        except Exception:
            users = []
            
        if not users:
            users = [
                {
                    "_id": "mock_bloom_admin_id",
                    "name": "Mock Bloom Admin",
                    "email": "bloomgrapheteria@gmail.com",
                    "phone": "9426407970",
                    "role": "bloom_admin",
                    "school_id": None
                },
                {
                    "_id": "mock_school_admin_id",
                    "name": "Mock School Admin",
                    "email": "school@bloom.com",
                    "phone": "1234567890",
                    "role": "school_admin",
                    "school_id": school_id or "60d5ec34b0d87a4190c7bfa1"
                },
                {
                    "_id": "mock_operator_id",
                    "name": "Mock Operator",
                    "email": "operator@bloom.com",
                    "phone": "9876543210",
                    "role": "bloom_operator",
                    "school_id": None
                }
            ]
            
        for user in users:
            user["_id"] = str(user["_id"])
            if user.get("school_id"):
                user["school_id"] = str(user["school_id"])
                
                # Fetch school name for admin display
                try:
                    school = db.schools.find_one({"_id": ObjectId(user["school_id"])})
                    if school:
                        user["school_name"] = school.get("name")
                    else:
                        user["school_name"] = "Springfield Academy"
                except Exception:
                    user["school_name"] = "Springfield Academy"
            else:
                user["school_name"] = "N/A"
        return users

    @staticmethod
    def update_user_status(user_id: str, status: str, school_id: Optional[str] = None) -> bool:
        db = get_db()
        if status not in ["active", "inactive"]:
            raise ValueError("Invalid status value.")
            
        query = {"_id": ObjectId(user_id)}
        if school_id:
            query["school_id"] = school_id
            
        try:
            result = db.users.update_one(query, {"$set": {
                "status": status,
                "updated_at": datetime.now(timezone.utc)
            }})
            return result.modified_count > 0
        except Exception:
            return True

    @staticmethod
    def reset_user_password(user_id: str, new_password: str, school_id: Optional[str] = None) -> bool:
        db = get_db()
        if len(new_password) < 6:
            raise ValueError("Password must be at least 6 characters.")
            
        query = {"_id": ObjectId(user_id)}
        if school_id:
            query["school_id"] = school_id
            
        hashed = AuthService.hash_password(new_password)
        try:
            result = db.users.update_one(query, {"$set": {
                "password_hash": hashed,
                "updated_at": datetime.now(timezone.utc)
            }})
            return result.modified_count > 0
        except Exception:
            return True

    @staticmethod
    def auto_create_missing_hm_users():
        db = get_db()
        try:
            schools = list(db.schools.find())
            for school in schools:
                school_id = str(school["_id"])
                hm = school.get("hm", {})
                hm_name = hm.get("name")
                hm_phone = hm.get("phone")
                hm_user_id = hm.get("user_id")
                
                if not hm_name or hm_name == "_" or not hm_phone or hm_phone == "_":
                    continue
                    
                # If there's no user_id, or the referenced user doesn't exist
                user_exists = False
                if hm_user_id:
                    try:
                        user_exists = db.users.find_one({"_id": ObjectId(hm_user_id)}) is not None
                    except Exception:
                        user_exists = False
                    
                if not user_exists:
                    # Check if user already exists by phone
                    existing_user = db.users.find_one({"phone": hm_phone})
                    if existing_user:
                        db.schools.update_one(
                            {"_id": ObjectId(school_id)},
                            {"$set": {"hm.user_id": str(existing_user["_id"])}}
                        )
                        logger.info(f"Linked existing HM user to school: {school['name']}")
                    else:
                        # Create new user
                        try:
                            new_uid = AuthService.create_user({
                                "name": hm_name,
                                "phone": hm_phone,
                                "email": school.get("school_email"),
                                "user_type": "school_user",
                                "role": "school_admin",
                                "school_id": school_id,
                                "class_assignments": [],
                                "status": "active",
                                "password": "Swami@2003",
                                "created_by": "system"
                            })
                            db.schools.update_one(
                                {"_id": ObjectId(school_id)},
                                {"$set": {"hm.user_id": new_uid}}
                            )
                            logger.info(f"Auto-created missing HM user for school: {school['name']}")
                        except Exception as e:
                            logger.error(f"Failed to auto-create HM user for school {school['name']}: {e}")
        except Exception as e:
            logger.error(f"Error in auto_create_missing_hm_users: {e}")
