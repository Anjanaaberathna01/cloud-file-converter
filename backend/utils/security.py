import os
import magic  # python-magic for MIME type checking  # pyright: ignore[reportMissingImports]
from fastapi import HTTPException, UploadFile  # pyright: ignore[reportMissingImports]

# Uploads සහ Outputs folders
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"

# Folders නැත්නම් auto create කරගැනීම
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 1. File Auto-Cleanup Function (Background Task)
def cleanup_file(file_path: str):
    """Safely delete a temporary file if it exists."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Error cleaning up file {file_path}: {e}")

# 2. PDF File Header (Magic Number) Validation
async def validate_pdf_file(file: UploadFile):
    """Ensure the uploaded file is genuinely a PDF by checking its binary header."""
    header = await file.read(2048)
    await file.seek(0)  # Reset file pointer back to start
    
    # PDF files always start with %PDF-
    if not header.startswith(b'%PDF-'):
        raise HTTPException(
            status_code=400, 
            detail="Invalid file format! The file is not a genuine PDF."
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