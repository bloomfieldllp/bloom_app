import os
import io
import json
import logging
import shutil
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone

logger = logging.getLogger("app.google_drive")

class GoogleDriveService:
    """
    Google Drive Service for managing ID Card Photos.
    Structure:
    ID Card Photos/
    ├── {School Name or Code}/
    │   ├── {Class Name}/
    │   │   ├── ABC001.jpg
    │   │   ├── ABC002.jpg
    │   │   └── Class1.xlsx
    │   │
    │   └── Correction Needed/
    │       ├── {Class Name}/
    │       │   ├── ABC001.jpg
    │       │   └── replacement_ABC001.jpg
    
    Supports both Google Drive API (when credentials are provided)
    and Local/Emulated Drive Storage (for testing, local dev, and offline storage).
    """

    ROOT_FOLDER_NAME = "ID Card Photos"
    CORRECTION_FOLDER_NAME = "Correction Needed"
    LOCAL_STORAGE_ROOT: Optional[str] = None
    
    @classmethod
    def get_base_storage_root(cls) -> str:
        if cls.LOCAL_STORAGE_ROOT:
            return cls.LOCAL_STORAGE_ROOT
        if os.environ.get("VERCEL") is not None or os.environ.get("AWS_LAMBDA_FUNCTION_NAME") is not None:
            return "/tmp/drive_storage"
        return os.environ.get("BLOOM_DRIVE_LOCAL_ROOT", os.path.join(os.path.dirname(os.path.dirname(__file__)), "drive_storage"))
    
    _folder_cache: Dict[str, str] = {}
    _file_cache: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_local_root(cls) -> str:
        root_path = os.path.join(cls.get_base_storage_root(), cls.ROOT_FOLDER_NAME)
        try:
            os.makedirs(root_path, exist_ok=True)
        except OSError:
            pass
        return root_path

    @classmethod
    def get_school_folder_path(cls, school_name_or_code: str) -> str:
        school_clean = str(school_name_or_code).replace("/", "_").replace("\\", "_").strip()
        path = os.path.join(cls.get_local_root(), school_clean)
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
        return path

    @classmethod
    def get_class_folder_path(cls, school_name_or_code: str, class_name: str) -> str:
        class_clean = str(class_name).replace("/", "_").replace("\\", "_").strip()
        path = os.path.join(cls.get_school_folder_path(school_name_or_code), class_clean)
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
        return path

    @classmethod
    def get_correction_folder_path(cls, school_name_or_code: str, class_name: str) -> str:
        class_clean = str(class_name).replace("/", "_").replace("\\", "_").strip()
        school_path = cls.get_school_folder_path(school_name_or_code)
        path = os.path.join(school_path, cls.CORRECTION_FOLDER_NAME, class_clean)
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
        return path

    @classmethod
    def get_drive_client(cls):
        """
        Builds Google Drive API v3 client from GOOGLE_SERVICE_ACCOUNT_JSON env
        or credentials/google-service-account.json file.
        """
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            SCOPES = ['https://www.googleapis.com/auth/drive']
            creds = None

            # 1. Check environment variable (raw JSON string)
            env_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
            if env_json:
                try:
                    info = json.loads(env_json)
                    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
                except Exception as je:
                    logger.warning(f"Failed to parse GOOGLE_SERVICE_ACCOUNT_JSON: {je}")

            # 2. Check credentials file
            if not creds:
                cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.path.join(
                    os.path.dirname(os.path.dirname(__file__)), "credentials", "google-service-account.json"
                )
                if os.path.exists(cred_path):
                    try:
                        creds = service_account.Credentials.from_service_account_file(cred_path, scopes=SCOPES)
                    except Exception as fe:
                        logger.warning(f"Failed to load service account file: {fe}")

            if creds:
                service = build('drive', 'v3', credentials=creds, cache_discovery=False)
                return service
        except Exception as e:
            logger.debug(f"Google Drive API client unavailable: {e}")
        return None

    @classmethod
    def sync_school_from_google_drive(cls, school_name_or_code: str, school_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Scans remote Google Drive for the school's folders and images,
        and caches their metadata into MongoDB for instant rendering and verification.
        """
        service = cls.get_drive_client()
        if not service:
            return []

        master_id = os.environ.get("GOOGLE_DRIVE_MASTER_FOLDER_ID", "1q1JKJSGE2DBqunn-hSHRAA_lfT3e5brC")
        if not master_id:
            return []

        synced_files = []
        try:
            # 1. List subfolders of Master Folder
            results = service.files().list(
                q=f"'{master_id}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'",
                fields="files(id, name)",
                pageSize=100
            ).execute()
            master_subfolders = results.get("files", [])

            # Check if there is a matching school folder
            school_folder_id = None
            clean_target = str(school_name_or_code).lower().strip()
            for f in master_subfolders:
                fn_clean = f["name"].lower().strip()
                if clean_target == fn_clean or clean_target in fn_clean or fn_clean in clean_target:
                    school_folder_id = f["id"]
                    break

            # If no school folder match, master folder might directly contain class folders
            class_folders = []
            if school_folder_id:
                class_res = service.files().list(
                    q=f"'{school_folder_id}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'",
                    fields="files(id, name)",
                    pageSize=100
                ).execute()
                class_folders = class_res.get("files", [])
            else:
                class_folders = master_subfolders

            from database import get_db
            db = get_db()
            IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

            for cf in class_folders:
                cname = cf["name"]
                if cname.lower() in [cls.CORRECTION_FOLDER_NAME.lower(), "correction needed", "corrections"]:
                    continue

                f_res = service.files().list(
                    q=f"'{cf['id']}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'",
                    fields="files(id, name, mimeType, size)",
                    pageSize=1000
                ).execute()
                files = f_res.get("files", [])

                for item in files:
                    fname = item["name"]
                    stem, ext = os.path.splitext(fname)
                    if ext.lower() in IMAGE_EXTS:
                        db.id_card_images.update_one(
                            {
                                "school_name_or_code": str(school_name_or_code).strip(),
                                "class_name": cname.strip(),
                                "file_stem": stem.lower().strip()
                            },
                            {
                                "$set": {
                                    "school_name_or_code": str(school_name_or_code).strip(),
                                    "school_id": str(school_id) if school_id else None,
                                    "class_name": cname.strip(),
                                    "filename": fname,
                                    "file_stem": stem.lower().strip(),
                                    "drive_file_id": item["id"],
                                    "content_type": item.get("mimeType", "image/jpeg"),
                                    "updated_at": datetime.now(timezone.utc).isoformat()
                                }
                            },
                            upsert=True
                        )
                        synced_files.append({
                            "name": fname,
                            "stem": stem.lower().strip(),
                            "class_name": cname.strip(),
                            "drive_file_id": item["id"]
                        })

            logger.info(f"Synced {len(synced_files)} ID card photos from Google Drive for {school_name_or_code}")
        except Exception as e:
            logger.error(f"Error syncing from Google Drive API: {e}")

        return synced_files

    @classmethod
    def list_class_files(cls, school_name_or_code: str, class_name: str) -> List[Dict[str, Any]]:
        """
        Lists all files in a class folder, extracting JPGs and Excel sheets.
        Returns a list of file metadata objects.
        """
        class_path = cls.get_class_folder_path(school_name_or_code, class_name)
        files = []
        if os.path.exists(class_path):
            for fname in sorted(os.listdir(class_path)):
                if fname.startswith("."):
                    continue
                fpath = os.path.join(class_path, fname)
                if os.path.isfile(fpath):
                    stem, ext = os.path.splitext(fname)
                    files.append({
                        "name": fname,
                        "stem": stem.lower().strip(),
                        "extension": ext.lower(),
                        "size": os.path.getsize(fpath),
                        "path": fpath,
                        "is_image": ext.lower() in [".jpg", ".jpeg", ".png", ".webp"],
                        "is_excel": ext.lower() in [".xlsx", ".xls", ".csv"]
                    })

        # Also pull from MongoDB cache (including Google Drive synced images)
        try:
            from database import get_db
            db = get_db()
            db_imgs = list(db.id_card_images.find({
                "$or": [
                    {"school_name_or_code": str(school_name_or_code).strip(), "class_name": str(class_name).strip()},
                    {"class_name": str(class_name).strip()}
                ]
            }, {"image_bytes": 0})) # Exclude massive binary payload when just listing
            
            existing_stems = {f["stem"] for f in files}
            for d in db_imgs:
                stem = d.get("file_stem", "").lower().strip()
                if stem and stem not in existing_stems:
                    files.append({
                        "name": d.get("filename", f"{stem}.jpg"),
                        "stem": stem,
                        "extension": os.path.splitext(d.get("filename", ".jpg"))[1].lower(),
                        "size": d.get("size", 0), # Default to 0 since we excluded bytes
                        "path": None,
                        "is_image": True,
                        "is_excel": False
                    })
                    existing_stems.add(stem)
        except Exception:
            pass

        return files

    @classmethod
    def find_id_card_jpg(cls, school_name_or_code: str, class_name: str, file_stem: str) -> Optional[Dict[str, Any]]:
        """
        Locates the complete generated ID-card JPG for a student by filename stem.
        Checks both original class folder and Correction Needed folder.
        """
        stem_clean = file_stem.lower().strip()
        
        # 1. Check in Class folder
        class_path = cls.get_class_folder_path(school_name_or_code, class_name)
        if os.path.exists(class_path):
            for fname in os.listdir(class_path):
                fstem, ext = os.path.splitext(fname)
                if fstem.lower().strip() == stem_clean and ext.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                    fpath = os.path.join(class_path, fname)
                    return {
                        "name": fname,
                        "stem": fstem,
                        "path": fpath,
                        "location": "CLASS_FOLDER",
                        "size": os.path.getsize(fpath),
                        "exists": True
                    }

        # 2. Check in Correction Needed folder
        corr_path = cls.get_correction_folder_path(school_name_or_code, class_name)
        if os.path.exists(corr_path):
            for fname in os.listdir(corr_path):
                if fname.startswith("replacement_"):
                    continue
                fstem, ext = os.path.splitext(fname)
                if fstem.lower().strip() == stem_clean and ext.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                    fpath = os.path.join(corr_path, fname)
                    return {
                        "name": fname,
                        "stem": fstem,
                        "path": fpath,
                        "location": "CORRECTION_FOLDER",
                        "size": os.path.getsize(fpath),
                        "exists": True
                    }

        return None

    @classmethod
    def move_id_card_to_correction(cls, school_name_or_code: str, class_name: str, file_stem_or_name: str) -> Dict[str, Any]:
        """
        Moves the complete generated ID card JPG from School/Class/ to School/Correction Needed/Class/.
        Idempotent: If the file is already in Correction Needed, succeeds without error.
        Preserves original filename, contents, and student mapping.
        """
        stem_input = os.path.splitext(file_stem_or_name)[0].lower().strip()
        
        corr_dir = cls.get_correction_folder_path(school_name_or_code, class_name)
        class_dir = cls.get_class_folder_path(school_name_or_code, class_name)
        
        # 1. Check if already in destination
        for fname in os.listdir(corr_dir):
            if fname.startswith("replacement_"):
                continue
            fstem, _ = os.path.splitext(fname)
            if fstem.lower().strip() == stem_input:
                dest_path = os.path.join(corr_dir, fname)
                logger.info(f"ID card {fname} is already in Correction Needed folder.")
                return {
                    "status": "already_moved",
                    "filename": fname,
                    "source_path": dest_path,
                    "dest_path": dest_path,
                    "moved": True
                }
                
        # 2. Find in source folder
        found_source = None
        for fname in os.listdir(class_dir):
            fstem, ext = os.path.splitext(fname)
            if fstem.lower().strip() == stem_input and ext.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                found_source = os.path.join(class_dir, fname)
                target_fname = fname
                break
                
        if not found_source:
            # Check if an exact filename was passed
            exact_source = os.path.join(class_dir, file_stem_or_name)
            if os.path.exists(exact_source):
                found_source = exact_source
                target_fname = file_stem_or_name
            else:
                logger.warning(f"Source ID card JPG for stem '{file_stem_or_name}' not found in class folder {class_dir}.")
                return {
                    "status": "not_found",
                    "filename": file_stem_or_name,
                    "source_path": None,
                    "dest_path": None,
                    "moved": False
                }
                
        # 3. Physically move file
        dest_path = os.path.join(corr_dir, target_fname)
        shutil.move(found_source, dest_path)
        logger.info(f"Successfully moved ID card JPG from {found_source} to {dest_path}")
        
        return {
            "status": "moved",
            "filename": target_fname,
            "source_path": found_source,
            "dest_path": dest_path,
            "moved": True
        }

    @classmethod
    def save_replacement_photo(
        cls,
        school_name_or_code: str,
        class_name: str,
        file_stem: str,
        photo_bytes: bytes,
        original_filename: str
    ) -> Dict[str, Any]:
        """
        Saves uploaded replacement student photograph into Correction Needed/{Class}/ folder.
        Uses deterministic naming: replacement_{file_stem}{ext}.
        Does NOT overwrite the original generated ID card.
        """
        corr_dir = cls.get_correction_folder_path(school_name_or_code, class_name)
        
        stem_clean = file_stem.lower().strip()
        _, ext = os.path.splitext(original_filename)
        if not ext:
            ext = ".jpg"
            
        replacement_filename = f"replacement_{stem_clean}{ext.lower()}"
        dest_path = os.path.join(corr_dir, replacement_filename)
        
        with open(dest_path, "wb") as f:
            f.write(photo_bytes)
            
        logger.info(f"Saved replacement photo to {dest_path}")
        return {
            "status": "saved",
            "filename": replacement_filename,
            "path": dest_path,
            "size": len(photo_bytes)
        }

    @classmethod
    def save_id_card_image(
        cls,
        school_name_or_code: str,
        class_name: str,
        filename: str,
        file_bytes: bytes,
        school_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Saves an uploaded ID card image to the school/class folder.
        Also caches to MongoDB (id_card_images) for persistent serverless cloud serving.
        """
        class_dir = cls.get_class_folder_path(school_name_or_code, class_name)
        safe_filename = os.path.basename(filename)
        dest_path = os.path.join(class_dir, safe_filename)
        
        try:
            with open(dest_path, "wb") as f:
                f.write(file_bytes)
        except Exception as e:
            logger.warning(f"Could not write image to local disk {dest_path}: {e}")
            
        file_stem = os.path.splitext(safe_filename)[0].lower().strip()
        ext = os.path.splitext(safe_filename)[1].lower()
        content_type = "image/jpeg"
        if ext == ".png":
            content_type = "image/png"
        elif ext == ".webp":
            content_type = "image/webp"

        # Cache in MongoDB
        try:
            from database import get_db
            db = get_db()
            db.id_card_images.update_one(
                {
                    "school_name_or_code": str(school_name_or_code).strip(),
                    "class_name": str(class_name).strip(),
                    "file_stem": file_stem
                },
                {
                    "$set": {
                        "school_name_or_code": str(school_name_or_code).strip(),
                        "school_id": str(school_id) if school_id else None,
                        "class_name": str(class_name).strip(),
                        "filename": safe_filename,
                        "file_stem": file_stem,
                        "content_type": content_type,
                        "image_bytes": file_bytes,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                },
                upsert=True
            )
        except Exception as dbe:
            logger.warning(f"Could not cache image in MongoDB: {dbe}")

        logger.info(f"Saved ID card image {safe_filename} for class {class_name} ({len(file_bytes)} bytes)")
        return {
            "status": "saved",
            "filename": safe_filename,
            "path": dest_path,
            "size": len(file_bytes),
            "file_stem": file_stem
        }

    @classmethod
    def get_id_card_bytes(cls, school_name_or_code: str, class_name: str, file_stem_or_name: str) -> Optional[Tuple[bytes, str]]:
        """
        Returns (bytes, content_type) for the requested ID card JPG.
        Checks local filesystem first, then MongoDB database cache.
        """
        found = cls.find_id_card_jpg(school_name_or_code, class_name, file_stem_or_name)
        if found and os.path.exists(found["path"]):
            ext = os.path.splitext(found["name"])[1].lower()
            content_type = "image/jpeg"
            if ext == ".png":
                content_type = "image/png"
            elif ext == ".webp":
                content_type = "image/webp"
                
            with open(found["path"], "rb") as f:
                data = f.read()
            return data, content_type
            
        # Fallback to MongoDB cache & Google Drive API download
        try:
            from database import get_db
            db = get_db()
            stem_clean = os.path.splitext(file_stem_or_name)[0].lower().strip()
            img_doc = db.id_card_images.find_one({
                "$or": [
                    {"school_name_or_code": str(school_name_or_code).strip(), "class_name": str(class_name).strip(), "file_stem": stem_clean},
                    {"class_name": str(class_name).strip(), "file_stem": stem_clean},
                    {"file_stem": stem_clean}
                ]
            })
            if img_doc:
                if img_doc.get("image_bytes"):
                    return bytes(img_doc["image_bytes"]), img_doc.get("content_type", "image/jpeg")
                    
                # Download on-demand from Google Drive if drive_file_id exists
                if img_doc.get("drive_file_id"):
                    service = cls.get_drive_client()
                    if service:
                        try:
                            file_data = service.files().get_media(fileId=img_doc["drive_file_id"]).execute()
                            if file_data:
                                # Cache in MongoDB for future instant loads
                                db.id_card_images.update_one(
                                    {"_id": img_doc["_id"]},
                                    {"$set": {"image_bytes": file_data}}
                                )
                                return bytes(file_data), img_doc.get("content_type", "image/jpeg")
                        except Exception as ge:
                            logger.error(f"Error downloading image from Drive API for {file_stem_or_name}: {ge}")
        except Exception as e:
            logger.debug(f"Error fetching image from DB cache: {e}")
            
        return None
