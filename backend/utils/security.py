import os
import uuid
from typing import Optional
from fastapi import HTTPException, UploadFile  # pyright: ignore[reportMissingImports]

# Uploads සහ Outputs folders නිර්මාණය කරගැනීම
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 1. File Auto-Cleanup Function (Background Task)
def cleanup_file(file_path: Optional[str]):
    """Safely delete a temporary file if it exists."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Error cleaning up file {file_path}: {e}")

# 2. File Header (Magic Number) & Type Validation
async def validate_file_header(file: UploadFile, allowed_types: list = ["pdf", "image", "word", "excel"]):
    """
    Ensure the uploaded file is genuinely matching its format by checking its binary header,
    preventing malicious file extension spoofing (e.g., malware.exe renamed to document.pdf).
    """
    header = await file.read(2048)
    await file.seek(0)  # Reset file pointer back to start

    # PDF Header Check (%PDF-)
    if "pdf" in allowed_types and header.startswith(b'%PDF-'):
        return True

    # Image Headers Check (PNG, JPEG, WEBP)
    if "image" in allowed_types:
        if header.startswith(b'\x89PNG\r\n\x1a\n') or header.startswith(b'\xff\xd8\xff') or (header.startswith(b'RIFF') and header[8:12] == b'WEBP'):
            return True

    # Office Documents (ZIP-based: docx, xlsx, pptx start with PK..)
    if any(t in allowed_types for t in ["word", "excel", "pptx"]):
        if header.startswith(b'PK\x03\x04'):
            return True

    # දැඩි ආරක්ෂාව සඳහා අනවසර හෝ නොගැලපෙන files block කිරීම
    raise HTTPException(
        status_code=400,
        detail="Invalid file format! The file content does not match a genuine document or image format."
    )

# 3. File Size Limit Validator (25MB Free Limit & Rs. 25 Micro-Payment Check)
def validate_file_size(file_size: int, is_pro: bool = False, has_paid_micro_fee: bool = False, max_size_mb: int = 25):
    """Check if file size exceeds free limit and trigger Rs. 25 micro-payment if needed."""
    max_bytes = max_size_mb * 1024 * 1024
    pro_max_bytes = 100 * 1024 * 1024  # Absolute 100MB limit

    # Absolute limit check (100MB පැනලා නම් කොහොමත් block කරනවා)
    if file_size > pro_max_bytes:
        raise HTTPException(
            status_code=400,
            detail="File size exceeds the maximum absolute limit (100MB)!"
        )

    # Free limit (25MB) පැනලා නම් සහ Pro user කෙනෙක් නෙමෙයි නම්:
    if file_size > max_bytes and not is_pro:
        # User Rs. 25 micro-payment එක කරලා නැත්නම් 402 error එක යවනවා
        if not has_paid_micro_fee:
            raise HTTPException(
                status_code=402,  # Payment Required status for micro-payment
                detail={
                    "error_code": "MICRO_PAYMENT_REQUIRED",
                    "message": f"ඔබගේ file එකේ සයිස් එක {round(file_size / (1024*1024), 2)}MB වේ (Free සීමාව {max_size_mb}MB කි).",
                    "cost_lkr": 25,
                    "suggestion": "මෙම විශාල file එක convert කරගැනීමට Rs. 25ක් ගෙවන්න හෝ අපේ Free PDF Compressor එක පාවිච්චි කරන්න."
                }
            )

# 4. Safe Unique Filename Generator (Path Traversal & Overwrite Protection)
def generate_safe_filename(original_filename: Optional[str]) -> str:
    """Generate a unique UUID filename to prevent path traversal and naming collisions."""
    ext = os.path.splitext(original_filename or "")[1].lower()
    return f"{uuid.uuid4()}{ext}"
