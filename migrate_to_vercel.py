import os
import io
from PIL import Image
import vercel_blob
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Connect to DB
mongo_uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
db_name = os.environ.get("MONGODB_DATABASE", "bloom_id_card")
client = MongoClient(mongo_uri)
db = client[db_name]
print(f"Connected to database: {db_name}")

def optimize_image_for_web(image_bytes, max_width=800, quality=80):
    """Converts raw image bytes to an optimized WebP."""
    img = Image.open(io.BytesIO(image_bytes))
    
    # Auto-rotate based on EXIF
    from PIL import ImageOps
    img = ImageOps.exif_transpose(img)
    
    # Resize if too large, maintaining aspect ratio
    if img.width > max_width:
        ratio = max_width / img.width
        new_size = (max_width, int(img.height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        
    # Convert to RGB if it's RGBA (WebP supports alpha, but RGB is safer for photos)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
        
    # Save to memory buffer as WebP
    out_buffer = io.BytesIO()
    img.save(out_buffer, format="WEBP", quality=quality, method=4)
    return out_buffer.getvalue()

def migrate_all():
    # Find all records that haven't been uploaded to Vercel Blob yet
    pending_records = list(db.id_card_records.find({
        "vercel_blob_url": {"$exists": False}
    }))
    
    print(f"Found {len(pending_records)} images to process...")
    
    for idx, record in enumerate(pending_records):
        print(f"[{idx+1}/{len(pending_records)}] Processing {record.get('file_stem')}...")
        
        # 1. Fetch raw image bytes from your existing Google Drive DB cache
        drive_img = db.id_card_images.find_one({
            "school_id": record["school_id"],
            "class_name": record["class_name"],
            "file_stem": record["file_stem"]
        })
        
        if not drive_img or "image_bytes" not in drive_img:
            print(f"  -> Skipping, no raw image bytes found.")
            continue
            
        raw_bytes = drive_img["image_bytes"]
        
        try:
            # 2. Compress & Convert to WebP
            webp_bytes = optimize_image_for_web(raw_bytes, max_width=800, quality=80)
            
            # 3. Upload to Vercel Blob
            filename = f"id_cards/{record['school_id']}/{record['class_name']}/{record['file_stem']}.webp"
            
            resp = vercel_blob.put(
                pathname=filename,
                data=webp_bytes,
                options={"access": "public", "contentType": "image/webp"}
            )
            
            blob_url = resp["url"]
            
            # 4. Update MongoDB Record
            db.id_card_records.update_one(
                {"_id": record["_id"]},
                {"$set": {"vercel_blob_url": blob_url}}
            )
            print(f"  -> Uploaded successfully: {blob_url}")
            
        except Exception as e:
            print(f"  -> ERROR processing image: {e}")

if __name__ == "__main__":
    migrate_all()
