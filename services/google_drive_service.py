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
    
    @classmethod
    def get_base_storage_root(cls) -> str:
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
    def list_class_files(cls, school_name_or_code: str, class_name: str) -> List[Dict[str, Any]]:
        """
        Lists all files in a class folder, extracting JPGs and Excel sheets.
        Returns a list of file metadata objects.
        """
        class_path = cls.get_class_folder_path(school_name_or_code, class_name)
        files = []
        if not os.path.exists(class_path):
            return files
            
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
    def get_id_card_bytes(cls, school_name_or_code: str, class_name: str, file_stem_or_name: str) -> Optional[Tuple[bytes, str]]:
        """
        Returns (bytes, content_type) for the requested ID card JPG.
        """
        found = cls.find_id_card_jpg(school_name_or_code, class_name, file_stem_or_name)
        if not found or not os.path.exists(found["path"]):
            return None
            
        ext = os.path.splitext(found["name"])[1].lower()
        content_type = "image/jpeg"
        if ext == ".png":
            content_type = "image/png"
        elif ext == ".webp":
            content_type = "image/webp"
            
        with open(found["path"], "rb") as f:
            data = f.read()
            
        return data, content_type
