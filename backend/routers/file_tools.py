from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks # pyright: ignore[reportMissingImports]
from typing import Optional
from utils.auth import verify_firebase_token
from utils.security import validate_file_size, validate_file_header, generate_safe_filename, cleanup_file
import os

router = APIRouter(prefix="/convert", tags=["File Conversion"])

@router.post("/process-file")
async def process_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    has_paid_micro_fee: bool = Form(False),
    user: Optional[dict] = Depends(verify_firebase_token) 
):
    contents = await file.read()
    file_size = len(contents)
    await file.seek(0)

    max_free_bytes = 25 * 1024 * 1024  # 25MB සීමාව

    # 1. 25MB සීමාව පැනලා නම්:
    if file_size > max_free_bytes:
        if not user:
            raise HTTPException(
                status_code=401,
                detail={
                    "error_code": "LOGIN_REQUIRED_FOR_LARGE_FILES",
                    "message": "25MB ට වැඩි ගොනු පරිවර්තනය කිරීමට කරුණාකර ඔබගේ ගිණුමට ලොග් වන්න."
                }
            )
        
        is_pro = user.get("is_pro", False) 
        validate_file_size(
            file_size=file_size,
            is_pro=is_pro,
            has_paid_micro_fee=has_paid_micro_fee,
            max_size_mb=25
        )

    # 2. Magic Number Check සහ ආරක්ෂිතව Save කිරීම
    await validate_file_header(file, allowed_types=["pdf", "image", "word", "excel"])
    safe_name = generate_safe_filename(file.filename)
    input_path = os.path.join("uploads", safe_name)
    
    with open(input_path, "wb") as buffer:
        buffer.write(contents)
        
    background_tasks.add_task(cleanup_file, input_path)

    # --- මෙතැනට ඔයාගේ අදාළ conversion logic එක ලියන්න ---
    output_filename = f"converted_{safe_name}"
    output_path = os.path.join("outputs", output_filename)
    # (උදාහරණයක් ලෙස file එක copy කිරීමක් කළ හැක)
    
    background_tasks.add_task(cleanup_file, output_path)

    from fastapi.responses import FileResponse # pyright: ignore[reportMissingImports]
    return FileResponse(output_path, filename=file.filename)