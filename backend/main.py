from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends  # pyright: ignore[reportMissingImports]
from fastapi.middleware.cors import CORSMiddleware  # pyright: ignore[reportMissingImports]
from fastapi.responses import FileResponse  # pyright: ignore[reportMissingImports]
from starlette.background import BackgroundTask  # pyright: ignore[reportMissingImports]
from PIL import Image, ImageEnhance  # pyright: ignore[reportMissingImports]
import io
import os
import time
import shutil
import uuid
import zipfile
from xml.sax.saxutils import escape
import fitz  # pyright: ignore[reportMissingImports]
import pandas as pd  # pyright: ignore[reportMissingImports, reportMissingModuleSource]
import pdfplumber  # pyright: ignore[reportMissingImports]
from pdf2docx import Converter  # pyright: ignore[reportMissingImports]
from docx2pdf import convert  # pyright: ignore[reportMissingImports]
from reportlab.lib.pagesizes import letter, landscape  # pyright: ignore[reportMissingImports, reportMissingModuleSource]
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer  # pyright: ignore[reportMissingImports, reportMissingModuleSource]
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # pyright: ignore[reportMissingImports, reportMissingModuleSource]
from reportlab.lib import colors  # pyright: ignore[reportMissingImports, reportMissingModuleSource]
from typing import Optional
from pptx import Presentation  # pyright: ignore[reportMissingImports]
from pptx.util import Inches  # pyright: ignore[reportMissingImports]
#from weasyprint import default_url_fetcher  # pyright: ignore[reportMissingImports]
from deep_translator import GoogleTranslator  # pyright: ignore[reportMissingImports]
from reportlab.pdfbase import pdfmetrics  # pyright: ignore[reportMissingImports, reportMissingModuleSource]
from reportlab.pdfbase.ttfonts import TTFont  # pyright: ignore[reportMissingImports, reportMissingModuleSource]


# comtypes works only on Windows (MS Office). Don't crash the whole app on other OS.
try:
    import comtypes.client  # pyright: ignore[reportMissingImports]
except ImportError:
    comtypes = None

from utils.security import validate_file_size, validate_file_header, generate_safe_filename, cleanup_file  # pyright: ignore
from utils.auth import verify_firebase_token  # pyright: ignore
from routers import payment, file_tools  # pyright: ignore


app = FastAPI(title="Cloud File Converter API")

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],  # frontend needs this to read the download filename
)

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

MAX_FILE_SIZE = 20 * 1024 * 1024
PRO_MAX_FILE_SIZE = 100 * 1024 * 1024

# Used to build download links (set BASE_URL in .env when you deploy)
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

A4_WIDTH, A4_HEIGHT = 1240, 1754  # A4 proportions at good resolution


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def cleanup_many(paths):
    for p in paths:
        cleanup_file(p)


def send_file(path: str, media_type: str, filename: str, extra_cleanup=()):
    """
    Return the file AND delete it only after the response has been fully sent.
    (Deleting inside `finally` removes the file before FastAPI streams it.)
    """
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        background=BackgroundTask(cleanup_many, [path, *extra_cleanup]),
    )


def make_input_path(file_id: str, filename: Optional[str], index: Optional[int] = None) -> str:
    """Build an upload path using only the base name of the client's filename."""
    safe = os.path.basename((filename or "upload").replace("\\", "/")) or "upload"
    prefix = f"{file_id}_{index}_" if index is not None else f"{file_id}_"
    return os.path.join(UPLOAD_DIR, prefix + safe)


def sweep_old_files(max_age_seconds: int = 3600):
    """Delete leftover temp files older than 1 hour (e.g. split-PDF download files)."""
    now = time.time()
    for folder in (UPLOAD_DIR, OUTPUT_DIR):
        for name in os.listdir(folder):
            p = os.path.join(folder, name)
            try:
                if os.path.isfile(p) and now - os.path.getmtime(p) > max_age_seconds:
                    os.remove(p)
            except OSError:
                pass


def images_to_a4_pdf(image_paths, output_path, enhance: bool = False) -> bool:
    """Put every image on a white A4 canvas (centered) and save them as one PDF."""
    processed_images = []
    for path in image_paths:
        with Image.open(path) as src:
            img = src.convert("RGB")

        if enhance:
            img = ImageEnhance.Contrast(img).enhance(1.5)
            img = ImageEnhance.Sharpness(img).enhance(1.3)

        canvas = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), (255, 255, 255))
        img.thumbnail((A4_WIDTH, A4_HEIGHT), Image.Resampling.LANCZOS)
        x = (A4_WIDTH - img.width) // 2
        y = (A4_HEIGHT - img.height) // 2
        canvas.paste(img, (x, y))
        processed_images.append(canvas)

    if not processed_images:
        return False

    processed_images[0].save(
        output_path,
        "PDF",
        save_all=True,
        append_images=processed_images[1:]
    )
    return True


def safe_url_fetcher(url, *args, **kwargs):
    """
    WeasyPrint would otherwise load file:// and http:// links found inside the
    uploaded HTML (local file read / SSRF). Only inline data: URLs are allowed.
    """
    if url.startswith("data:"):
        return default_url_fetcher(url)
    raise ValueError(f"External resource blocked: {url}")


sweep_old_files()


@app.get("/")
def read_root():
    return {"status": "File Converter API is running!"}

# Include the payment router for handling mock payments and PayHere integration
app.include_router(payment.router, prefix="/api/payment", tags=["Payment & Mock Checkout"])
app.include_router(file_tools.router, prefix="/api", tags=["File Conversion & Tools"])

# Generic Conversion Endpoint (Micro-Payment & Size Check using security.py)
@app.post("/convert/generic-conversion")
async def generic_conversion(
    file: UploadFile = File(...),
    is_pro: bool = Form(False),             # Pro user ද නැද්ද කියලා බලන්න
    has_paid_micro_fee: bool = Form(False)  # User Rs. 25 ගෙවලා නම් True කියලා එනවා
):
    contents = await file.read()
    file_size = len(contents)

    # security.py එකේ තියෙන validate_file_size function එක මඟින්
    # 25MB සීමාව, 100MB Pro සීමාව සහ Rs. 25 Micro-payment check එක එකවර සිදු කරයි.
    validate_file_size(file_size, is_pro=is_pro, has_paid_micro_fee=has_paid_micro_fee)

    # ---------------------------------------------------------
    # Free සීමාව ඇතුළේ නම් හෝ user Rs. 25 ගෙවලා / Pro user කෙනෙක් නම්
    # conversion වැඩේ මෙතනින් ඉදිරියට කරගෙන යන්න පුළුවන්...
    # ---------------------------------------------------------

    return {
        "status": "success",
        "message": f"File size validated successfully ({round(file_size / (1024*1024), 2)}MB). Ready for conversion!"
    }

# 1. Image Conversion Endpoint
@app.post("/convert/image")
async def convert_image(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_format: str = Form(...)
):
    file_id = str(uuid.uuid4())
    input_path = make_input_path(file_id, file.filename)
    output_path = None

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    background_tasks.add_task(cleanup_file, input_path)

    try:
        target_ext = target_format.lower().strip()
        if not target_ext.isalnum():
            raise HTTPException(status_code=400, detail="Invalid target format!")

        with Image.open(input_path) as src:
            img = src
            if target_ext in ["jpeg", "jpg"]:
                img = src.convert("RGB")
                target_ext = "jpeg"

            output_filename = f"{file_id}_converted.{target_ext}"
            output_path = os.path.join(OUTPUT_DIR, output_filename)
            img.save(output_path, target_ext.upper())

        background_tasks.add_task(cleanup_file, output_path)

        return FileResponse(output_path, media_type=f"image/{target_ext}", filename=f"converted_image.{target_ext}")

    except HTTPException:
        cleanup_many([input_path, output_path])
        raise
    except Exception as e:
        cleanup_many([input_path, output_path])
        raise HTTPException(status_code=400, detail=str(e))

# 2. PDF to Word Endpoint
@app.post("/convert/pdf-to-word")
async def convert_pdf_to_word(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    input_path = make_input_path(file_id, file.filename)
    output_path = os.path.join(OUTPUT_DIR, f"{file_id}_converted.docx")

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        cv = Converter(input_path)
        try:
            cv.convert(output_path, start=0, end=None)
        finally:
            cv.close()

        return send_file(output_path, DOCX_MIME, "converted_document.docx")

    except Exception as e:
        cleanup_file(output_path)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cleanup_file(input_path)

# 3. Word to PDF Endpoint
@app.post("/convert/word-to-pdf")
async def convert_word_to_pdf(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    input_path = make_input_path(file_id, file.filename)
    output_path = os.path.join(OUTPUT_DIR, f"{file_id}_converted.pdf")

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # docx2pdf uses MS Word installed on Windows in the background
        convert(input_path, output_path)

        return send_file(output_path, "application/pdf", "converted_document.pdf")

    except Exception as e:
        cleanup_file(output_path)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cleanup_file(input_path)

# 4. Multiple Images to PDF Endpoint with Uniform Size (A4 Standard Canvas)
@app.post("/convert/images-to-pdf")
async def convert_images_to_pdf(files: list[UploadFile] = File(...)):
    file_id = str(uuid.uuid4())
    saved_image_paths = []
    total_size = 0
    output_path = None

    try:
        for i, file in enumerate(files):
            contents = await file.read()
            total_size += len(contents)

            if total_size > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail="Total files size exceeds the 20MB limit!")

            input_path = make_input_path(file_id, file.filename, i)
            with open(input_path, "wb") as f:
                f.write(contents)
            saved_image_paths.append(input_path)

        output_path = os.path.join(OUTPUT_DIR, f"{file_id}_converted.pdf")

        if not images_to_a4_pdf(saved_image_paths, output_path):
            raise HTTPException(status_code=400, detail="No valid images provided")

        return send_file(output_path, "application/pdf", "merged_images.pdf")

    except HTTPException:
        cleanup_file(output_path)
        raise
    except Exception as e:
        cleanup_file(output_path)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cleanup_many(saved_image_paths)

# 5. Excel to PDF Endpoint
@app.post("/convert/excel-to-pdf")
async def convert_excel_to_pdf(file: UploadFile = File(...)):
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds the 20MB limit!")

    file_id = str(uuid.uuid4())
    input_path = make_input_path(file_id, file.filename)
    output_path = os.path.join(OUTPUT_DIR, f"{file_id}_converted.pdf")

    with open(input_path, "wb") as f:
        f.write(contents)

    try:
        # Read Excel file using pandas
        df = pd.read_excel(input_path)
        df = df.fillna("")  # Replace NaN with empty strings

        # Setup PDF document (Landscape for wide spreadsheets)
        doc = SimpleDocTemplate(output_path, pagesize=landscape(letter))
        elements = []

        # Add Title style
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'ExcelTitle',
            parent=styles['Heading1'],
            fontSize=14,
            textColor=colors.HexColor('#1e293b'),
            spaceAfter=15
        )
        elements.append(Paragraph(f"Converted Report: {escape(file.filename or '')}", title_style))

        # Convert DataFrame to list of lists for ReportLab Table
        data = [df.columns.tolist()] + df.values.tolist()

        # Build Table with formatting
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3b82f6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))

        elements.append(table)
        doc.build(elements)

        return send_file(output_path, "application/pdf", "converted_spreadsheet.pdf")

    except Exception as e:
        cleanup_file(output_path)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cleanup_file(input_path)

# 6. PDF to Excel Endpoint
@app.post("/convert/pdf-to-excel")
async def convert_pdf_to_excel(file: UploadFile = File(...)):
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds the 20MB limit!")

    file_id = str(uuid.uuid4())
    input_path = make_input_path(file_id, file.filename)
    output_path = os.path.join(OUTPUT_DIR, f"{file_id}_converted.xlsx")

    with open(input_path, "wb") as f:
        f.write(contents)

    try:
        all_tables = []

        # Open PDF with pdfplumber and extract tables from all pages
        with pdfplumber.open(input_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        all_tables.append(row)

        if not all_tables:
            raise HTTPException(status_code=400, detail="No tabular data found in the PDF!")

        # Convert extracted table data to Pandas DataFrame
        # First row is usually headers
        df = pd.DataFrame(all_tables[1:], columns=all_tables[0])

        # Save to Excel
        df.to_excel(output_path, index=False)

        return send_file(output_path, XLSX_MIME, "converted_table.xlsx")

    except HTTPException:
        cleanup_file(output_path)
        raise
    except Exception as e:
        cleanup_file(output_path)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cleanup_file(input_path)

# 7. Advanced PDF to Images (With Specific Page Selection)
@app.post("/convert/pdf-to-selected-images")
async def convert_pdf_to_selected_images(
    file: UploadFile = File(...),
    pages: Optional[str] = Form(None)  # Example input: "2, 6" or leave blank for all
):
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds the 20MB limit!")

    file_id = str(uuid.uuid4())
    input_path = make_input_path(file_id, file.filename)

    with open(input_path, "wb") as f:
        f.write(contents)

    extracted_image_paths = []
    zip_path = None

    try:
        with fitz.open(input_path) as doc:
            total_pages = len(doc)

            # Parse specific pages if provided (e.g., "2, 6" -> [1, 5] because 0-indexed)
            target_page_indices = []
            if pages:
                try:
                    # Split by comma and convert to 0-based index
                    for p in pages.split(","):
                        p_num = int(p.strip())
                        if 1 <= p_num <= total_pages:
                            target_page_indices.append(p_num - 1)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid page numbers format! Use comma-separated numbers (e.g., 2,6).")
            else:
                # If no pages specified, convert all pages
                target_page_indices = list(range(total_pages))

            if not target_page_indices:
                raise HTTPException(status_code=400, detail="No valid pages selected!")

            # Extract selected pages
            for page_idx in target_page_indices:
                page = doc[page_idx]
                pix = page.get_pixmap(dpi=150)  # High resolution rendering

                img_filename = f"{file_id}_page_{page_idx + 1}.png"
                img_path = os.path.join(OUTPUT_DIR, img_filename)
                pix.save(img_path)
                extracted_image_paths.append(img_path)

        # If only 1 image extracted, return it directly
        if len(extracted_image_paths) == 1:
            return send_file(
                extracted_image_paths[0],
                "image/png",
                f"page_{target_page_indices[0] + 1}.png"
            )

        # If multiple images, bundle them into a ZIP file
        zip_path = os.path.join(OUTPUT_DIR, f"{file_id}_selected_images.zip")

        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for img_path in extracted_image_paths:
                zipf.write(img_path, arcname=os.path.basename(img_path))

        # Individual PNGs are no longer needed once they are inside the ZIP
        cleanup_many(extracted_image_paths)

        return send_file(zip_path, "application/zip", "selected_pdf_images.zip")

    except HTTPException:
        cleanup_many([*extracted_image_paths, zip_path])
        raise
    except Exception as e:
        cleanup_many([*extracted_image_paths, zip_path])
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cleanup_file(input_path)

# 8. PowerPoint (.pptx) to PDF Endpoint (Windows MS Office required)
@app.post("/convert/pptx-to-pdf")
async def convert_pptx_to_pdf(file: UploadFile = File(...)):
    if comtypes is None:
        raise HTTPException(status_code=501, detail="PPTX to PDF needs Windows with MS PowerPoint installed.")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds the 20MB limit!")

    file_id = str(uuid.uuid4())
    input_path = make_input_path(file_id, file.filename)
    output_path = os.path.join(OUTPUT_DIR, f"{file_id}_converted.pdf")

    with open(input_path, "wb") as f:
        f.write(contents)

    try:
        # Initialize PowerPoint COM object
        powerpoint = comtypes.client.CreateObject("Powerpoint.Application")
        powerpoint.Visible = 1
        deck = None

        try:
            # Open presentation and export as PDF (Format 32 = ppSaveAsPDF)
            deck = powerpoint.Presentations.Open(os.path.abspath(input_path))
            deck.SaveAs(os.path.abspath(output_path), 32)
        finally:
            # Always close PowerPoint, otherwise a hidden POWERPNT.EXE stays running on errors
            if deck is not None:
                deck.Close()
            powerpoint.Quit()

        return send_file(output_path, "application/pdf", "converted_presentation.pdf")
    except Exception as e:
        cleanup_file(output_path)
        raise HTTPException(status_code=400, detail=f"PPT conversion error: {str(e)}")
    finally:
        cleanup_file(input_path)


# 9. PDF to PowerPoint (.pptx) Endpoint
@app.post("/convert/pdf-to-pptx")
async def convert_pdf_to_pptx(file: UploadFile = File(...)):
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds the 20MB limit!")

    file_id = str(uuid.uuid4())
    input_path = make_input_path(file_id, file.filename)
    output_path = os.path.join(OUTPUT_DIR, f"{file_id}_converted.pptx")

    with open(input_path, "wb") as f:
        f.write(contents)

    try:
        prs = Presentation()
        # Set slide dimensions to widescreen (16:9)
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        blank_slide_layout = prs.slide_layouts[6]  # Blank layout

        with fitz.open(input_path) as doc:
            for page_num in range(len(doc)):
                page = doc[page_num]
                pix = page.get_pixmap(dpi=150)

                img_path = os.path.join(UPLOAD_DIR, f"{file_id}_slide_{page_num}.png")
                pix.save(img_path)

                try:
                    # Add slide and insert page image to fit the slide
                    slide = prs.slides.add_slide(blank_slide_layout)
                    slide.shapes.add_picture(img_path, 0, 0, width=prs.slide_width, height=prs.slide_height)
                finally:
                    # Cleanup temp image
                    cleanup_file(img_path)

        prs.save(output_path)

        return send_file(output_path, PPTX_MIME, "converted_presentation.pptx")
    except Exception as e:
        cleanup_file(output_path)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cleanup_file(input_path)

# 10. Scan to PDF Endpoint (Enhanced for Scanned Document Look)
@app.post("/convert/scan-to-pdf")
async def convert_scan_to_pdf(
    files: list[UploadFile] = File(...),
    enhance: Optional[bool] = Form(True)  # Option to boost contrast for text clarity
):
    file_id = str(uuid.uuid4())
    saved_image_paths = []
    total_size = 0
    output_path = None

    try:
        for i, file in enumerate(files):
            contents = await file.read()
            total_size += len(contents)

            if total_size > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail="Total files size exceeds the 20MB limit!")

            input_path = make_input_path(file_id, file.filename, i)
            with open(input_path, "wb") as f:
                f.write(contents)
            saved_image_paths.append(input_path)

        output_path = os.path.join(OUTPUT_DIR, f"{file_id}_scanned.pdf")

        if not images_to_a4_pdf(saved_image_paths, output_path, enhance=bool(enhance)):
            raise HTTPException(status_code=400, detail="No valid scanned images provided")

        return send_file(output_path, "application/pdf", "scanned_document.pdf")

    except HTTPException:
        cleanup_file(output_path)
        raise
    except Exception as e:
        cleanup_file(output_path)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cleanup_many(saved_image_paths)

# 11. HTML to PDF Endpoint (Using WeasyPrint) - Temporarily Disabled
# @app.post("/convert/html-to-pdf")
# async def convert_html_to_pdf(file: UploadFile = File(...)):
#     contents = await file.read()
#     if len(contents) > MAX_FILE_SIZE:
#         raise HTTPException(status_code=400, detail="File size exceeds the 20MB limit!")
# 
#     file_id = str(uuid.uuid4())
#     output_path = os.path.join(OUTPUT_DIR, f"{file_id}_converted.pdf")
# 
#     try:
#         # Convert uploaded HTML to PDF using WeasyPrint (external/local resources are blocked)
#         # HTML(file_obj=io.BytesIO(contents), url_fetcher=safe_url_fetcher).write_pdf(output_path)
# 
#         # return send_file(output_path, "application/pdf", "converted_webpage.pdf")
#         pass
#     except Exception as e:
#         cleanup_file(output_path)
#         raise HTTPException(status_code=400, detail=f"HTML conversion error: {str(e)}")


@app.post("/convert/pdf-translate")
async def pdf_translate(
    file: UploadFile = File(...),
    source_lang: str = Form(...),  # e.g., 'si', 'ta', 'en'
    target_lang: str = Form(...)   # e.g., 'en', 'si', 'ta'
):
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds the 20MB limit!")

    file_id = str(uuid.uuid4())
    input_path = make_input_path(file_id, file.filename)
    output_path = os.path.join(OUTPUT_DIR, f"{file_id}_translated.pdf")

    with open(input_path, "wb") as f:
        f.write(contents)

    try:
        extracted_text_blocks = []

        # 1. Extract text from PDF using pdfplumber
        with pdfplumber.open(input_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    extracted_text_blocks.append(text)

        if not extracted_text_blocks:
            raise HTTPException(status_code=400, detail="No readable text found in the PDF!")

        full_text = "\n\n".join(extracted_text_blocks)

        # 2. Translate text using deep-translator (with batching & rate-limit protection)

        translator = GoogleTranslator(source=source_lang, target=target_lang)

        # Split text into small chunks (around 1000-2000 characters per chunk)
        chunks = [full_text[i:i+1500] for i in range(0, len(full_text), 1500)]
        translated_chunks = []

        for chunk in chunks:
            if chunk.strip():
                try:

                    res = translator.translate(chunk)
                    translated_chunks.append(res or "")
                except Exception as ex:
                    # මොකක් හෝ රික්වෙස්ට් ප්‍රශ්නයක් ආවොත් තත්පර 2ක් ඉඳලා ආපහු ට්‍රයි කරන්න පුළුවන්
                    time.sleep(2)
                    res = translator.translate(chunk)
                    translated_chunks.append(res or "")
                
                # Google rate-limit එක මඟහරවා ගැනීමට සෑම රික්වෙස්ට් එකක් අතරතුරම තත්පර 1.2ක විවේකයක්
                time.sleep(1.2)

        final_translated_text = "\n\n".join(translated_chunks)

        # ඔබේ backend ෆෝල්ඩර් එකේ මෙම ෆොන්ට් ෆයිල්ස් තිබිය යුතුය.
        sinhala_font_path = "4u-ganganee.ttf"
        tamil_font_path = "VANAVIL-Avvaiyar Regular.otf"
        
        active_font = "Helvetica" # Default fallback font

        if target_lang == "si" and os.path.exists(sinhala_font_path):
            try:
                pdfmetrics.registerFont(TTFont("SinhalaCustomFont", sinhala_font_path))
                active_font = "SinhalaCustomFont"
            except Exception as e:
                print(f"Sinhala font registration error: {e}")
                
        elif target_lang == "ta" and os.path.exists(tamil_font_path):
            try:
                # .otf හෝ .ttf සඳහා TTFont class එකම පාවිච්චි කළ හැක
                pdfmetrics.registerFont(TTFont("TamilCustomFont", tamil_font_path))
                active_font = "TamilCustomFont"
            except Exception as e:
                print(f"Tamil font registration error: {e}")

        # 4. Generate a clean new PDF with the translated text using ReportLab
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        elements = []

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'TransTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor("#1e293b"),
            spaceAfter=15
        )
        
        body_style = ParagraphStyle(
            'TransBody',
            parent=styles['Normal'],
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#334155"),
            spaceAfter=10,
            fontName=active_font  # Dynamic font assignment (Sinhala, Tamil or Helvetica)
        )

        elements.append(Paragraph(
            f"Translated Document ({escape(source_lang.upper())} to {escape(target_lang.upper())})",
            title_style
        ))
        elements.append(Spacer(1, 10))

        # ReportLab Paragraph reads XML, so escape special characters
        for paragraph in final_translated_text.split("\n"):
            if paragraph.strip():
                elements.append(Paragraph(escape(paragraph.strip()), body_style))

        doc.build(elements)

        return send_file(output_path, "application/pdf", f"translated_{source_lang}_to_{target_lang}.pdf")

    except HTTPException:
        cleanup_file(output_path)
        raise
    except Exception as e:
        cleanup_file(output_path)
        raise HTTPException(status_code=400, detail=f"Translation error: {str(e)}")
    finally:
        cleanup_file(input_path)

# 13. Organize PDF Pages Endpoint (Reorder Pages)
@app.post("/convert/organize-pdf")
async def organize_pdf(
    file: UploadFile = File(...),
    new_order: str = Form(...)  # Comma-separated page numbers, e.g., "3,1,2"
):
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds the 20MB limit!")

    file_id = str(uuid.uuid4())
    input_path = make_input_path(file_id, file.filename)
    output_path = os.path.join(OUTPUT_DIR, f"{file_id}_organized.pdf")

    with open(input_path, "wb") as f:
        f.write(contents)

    try:
        with fitz.open(input_path) as doc:
            total_pages = len(doc)

            # Parse new order string (e.g., "3,1,2" -> [2, 0, 1] for 0-indexed)
            try:
                order_indices = []
                for p in new_order.split(","):
                    p_num = int(p.strip())
                    if 1 <= p_num <= total_pages:
                        order_indices.append(p_num - 1)
                    else:
                        raise HTTPException(status_code=400, detail=f"Invalid page number {p}!")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid page order format! Use comma-separated numbers (e.g., 3,1,2).")

            if len(order_indices) != total_pages:
                raise HTTPException(status_code=400, detail=f"You must specify all {total_pages} page numbers in the new order!")

            # Create a new empty PDF
            new_doc = fitz.open()

            # Insert pages in the user's requested order
            for idx in order_indices:
                new_doc.insert_pdf(doc, from_page=idx, to_page=idx)

            new_doc.save(output_path)
            new_doc.close()

        return send_file(output_path, "application/pdf", "organized_document.pdf")

    except HTTPException:
        cleanup_file(output_path)
        raise
    except Exception as e:
        cleanup_file(output_path)
        raise HTTPException(status_code=400, detail=f"Organize PDF error: {str(e)}")
    finally:
        cleanup_file(input_path)

# 14. Merge Multiple PDFs Endpoint
@app.post("/convert/merge-pdfs")
async def merge_pdfs(files: list[UploadFile] = File(...)):
    file_id = str(uuid.uuid4())
    saved_paths = []
    total_size = 0
    output_path = None
    merged_doc = None

    try:
        # Create an empty master PDF document for merging
        merged_doc = fitz.open()

        for i, file in enumerate(files):
            contents = await file.read()
            total_size += len(contents)

            if total_size > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail="Total files size exceeds the 20MB limit!")

            input_path = make_input_path(file_id, file.filename, i)
            with open(input_path, "wb") as f:
                f.write(contents)
            saved_paths.append(input_path)

            # Open each PDF and append its pages to the master merged document
            with fitz.open(input_path) as doc:
                merged_doc.insert_pdf(doc)

        output_path = os.path.join(OUTPUT_DIR, f"{file_id}_merged.pdf")

        merged_doc.save(output_path)

        return send_file(output_path, "application/pdf", "merged_document.pdf")

    except HTTPException:
        cleanup_file(output_path)
        raise
    except Exception as e:
        cleanup_file(output_path)
        raise HTTPException(status_code=400, detail=f"Merge PDFs error: {str(e)}")
    finally:
        if merged_doc is not None:
            merged_doc.close()
        # Cleanup temporary input files
        cleanup_many(saved_paths)

# 14. Split PDF into Multiple Parts Endpoint (With Download Links)
@app.post("/convert/split-pdf-links")
async def split_pdf_links(
    file: UploadFile = File(...),
    split_ranges: str = Form(...)  # e.g., "1-3, 4-6" or individual pages
):
    sweep_old_files()

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Total files size exceeds the 20MB limit!")

    file_id = str(uuid.uuid4())
    input_path = make_input_path(file_id, file.filename)

    with open(input_path, "wb") as f:
        f.write(contents)

    response_links = []
    split_pdf_paths = []
    zip_path = None

    try:
        with fitz.open(input_path) as doc:
            total_pages = len(doc)

            # Parse ranges like "1-3, 4-5" or comma-separated numbers
            ranges = [r.strip() for r in split_ranges.split(",")]

            for i, rng in enumerate(ranges):
                try:
                    if "-" in rng:
                        start_p, end_p = map(int, rng.split("-"))
                        from_idx = max(0, start_p - 1)
                        to_idx = min(total_pages - 1, end_p - 1)
                        part_name = f"Part_{i+1}_Pages_{start_p}_to_{end_p}.pdf"
                    else:
                        p_num = int(rng)
                        if not (1 <= p_num <= total_pages):
                            continue
                        from_idx = to_idx = p_num - 1
                        part_name = f"Part_{i+1}_Page_{p_num}.pdf"
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Invalid split range '{rng}'! Use e.g. 1-3, 5")

                part_filename = f"{file_id}_{part_name}"
                part_path = os.path.join(OUTPUT_DIR, part_filename)

                sub_doc = fitz.open()
                sub_doc.insert_pdf(doc, from_page=from_idx, to_page=to_idx)
                sub_doc.save(part_path)
                sub_doc.close()
                split_pdf_paths.append((part_path, part_name))

                # Add individual download URL
                response_links.append({
                    "title": f"Part {i+1} ({rng})",
                    "filename": part_name,
                    "url": f"{BASE_URL}/download-file/{part_filename}"
                })

        if not response_links:
            raise HTTPException(status_code=400, detail="Invalid split ranges provided!")

        # Bundle all into a ZIP file for a "Download All" option
        zip_filename = f"{file_id}_all_parts.zip"
        zip_path = os.path.join(OUTPUT_DIR, zip_filename)
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for path, name in split_pdf_paths:
                zipf.write(path, arcname=name)

        all_download_url = f"{BASE_URL}/download-file/{zip_filename}"

        # The parts + ZIP must stay on disk so the links work (old files are swept after 1 hour)
        return {
            "status": "success",
            "parts": response_links,
            "download_all_url": all_download_url
        }

    except HTTPException:
        cleanup_many([p for p, _ in split_pdf_paths])
        cleanup_file(zip_path)
        raise
    except Exception as e:
        cleanup_many([p for p, _ in split_pdf_paths])
        cleanup_file(zip_path)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cleanup_file(input_path)

# Serve individual or zip generated files
@app.get("/download-file/{filename}")
async def download_file(filename: str):
    # Block path tricks like "..\\main.py" (backslash works as a separator on Windows)
    safe_name = os.path.basename(filename.replace("\\", "/"))
    if safe_name != filename:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = os.path.join(OUTPUT_DIR, safe_name)
    if os.path.isfile(file_path):
        # Clean up internal uuid prefix for the actual downloaded filename
        clean_name = safe_name.split("_", 1)[1] if "_" in safe_name else safe_name
        return FileResponse(file_path, filename=clean_name)
    raise HTTPException(status_code=404, detail="File not found")

# 15. Compress PDF Endpoint (With User Authentication for Large Files)
@app.post("/convert/compress-pdf")
async def compress_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    has_paid_micro_fee: bool = Form(False),
    user: Optional[dict] = Depends(verify_firebase_token)
):
    contents = await file.read()
    file_size = len(contents)
    await file.seek(0)

    max_free_bytes = 25 * 1024 * 1024  # 25MB සීමාව

    # 1. 25MB සීමාව පැනලා නම් ලොගින් වීම පරීක්ෂා කිරීම
    if file_size > max_free_bytes:
        if not user:
            raise HTTPException(
                status_code=401,
                detail={
                    "error_code": "LOGIN_REQUIRED_FOR_LARGE_FILES",
                    "message": "25MB ට වැඩි ගොනු කොම්ප්‍රෙස් කිරීමට කරුණාකර ඔබගේ ගිණුමට ලොග් වන්න."
                }
            )

        is_pro = user.get("is_pro", False)
        validate_file_size(
            file_size=file_size,
            is_pro=is_pro,
            has_paid_micro_fee=has_paid_micro_fee,
            max_size_mb=25
        )

    # 2. PDF Header (Magic Number) Validation
    await validate_file_header(file, allowed_types=["pdf"])

    # 3. ආරක්ෂිතව ෆයිල් එක සේව් කිරීම
    safe_name = generate_safe_filename(file.filename)
    input_path = os.path.join(UPLOAD_DIR, safe_name)

    with open(input_path, "wb") as buffer:
        buffer.write(contents)

    background_tasks.add_task(cleanup_file, input_path)

    output_filename = f"compressed_{safe_name}"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    try:
        # PyMuPDF මඟින් PDF එක Compress කිරීම
        with fitz.open(input_path) as doc:
            doc.save(output_path, garbage=4, deflate=True, clean=True)

        # Response යැවුණාට පස්සේ ෆයිල්ස් ස්වයංක්‍රීයව delete වීමට
        background_tasks.add_task(cleanup_file, output_path)

        return FileResponse(output_path, filename=f"compressed_{file.filename}")

    except Exception as e:
        cleanup_many([input_path, output_path])
        raise HTTPException(status_code=500, detail=f"PDF Compression failed: {str(e)}")
