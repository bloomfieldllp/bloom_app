import os
import io
import logging
from typing import Optional
from PIL import Image, ImageOps

logger = logging.getLogger("app.image_pipeline")

class ImagePipelineService:
    @staticmethod
    def optimize_to_webp(image_bytes: bytes, max_width: int = 800, quality: int = 80) -> bytes:
        """Converts raw image bytes to an optimized WebP."""
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)
        
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        out_buffer = io.BytesIO()
        img.save(out_buffer, format="WEBP", quality=quality, method=4)
        return out_buffer.getvalue()

    @staticmethod
    def upload_to_vercel_blob(pathname: str, image_bytes: bytes) -> Optional[str]:
        """Uploads image bytes to Vercel Blob CDN if BLOB_READ_WRITE_TOKEN is configured."""
        token = os.environ.get("BLOB_READ_WRITE_TOKEN")
        if not token:
            logger.debug("BLOB_READ_WRITE_TOKEN not set; skipping Vercel Blob upload.")
            return None
            
        try:
            import vercel_blob
            resp = vercel_blob.put(
                pathname=pathname,
                data=image_bytes,
                options={"access": "public", "contentType": "image/webp"}
            )
            return resp.get("url")
        except Exception as e:
            logger.error(f"Vercel Blob upload failed for {pathname}: {e}")
            return None

    @classmethod
    def process_and_store_card_image(
        cls,
        school_id: str,
        class_name: str,
        file_stem: str,
        raw_bytes: bytes,
        card_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Compresses raw image bytes to WebP and uploads to Vercel Blob.
        Updates the matching id_card_record in MongoDB with vercel_blob_url.
        """
        if not os.environ.get("BLOB_READ_WRITE_TOKEN"):
            return None
            
        try:
            webp_bytes = cls.optimize_to_webp(raw_bytes, max_width=800, quality=80)
            pathname = f"id_cards/{school_id}/{class_name}/{file_stem}.webp"
            blob_url = cls.upload_to_vercel_blob(pathname, webp_bytes)
            
            if blob_url:
                from database import get_db
                db = get_db()
                query = {"_id": card_id} if card_id else {"school_id": str(school_id), "class_name": class_name, "file_stem": file_stem}
                db.id_card_records.update_one(query, {"$set": {"vercel_blob_url": blob_url}})
                logger.info(f"Processed and uploaded WebP for {file_stem} to Vercel Blob: {blob_url}")
                return blob_url
        except Exception as e:
            logger.error(f"Failed image pipeline processing for {file_stem}: {e}")
            
        return None
