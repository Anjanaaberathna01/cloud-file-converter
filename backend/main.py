from fastapi import FastAPI, UploadFile, File, Form, HTTPException # pyright: ignore[reportMissingImports]
from fastapi.middleware.cors import CORSMiddleware  # pyright: ignore[reportMissingImports]
from fastapi.responses import FileResponse  # pyright: ignore[reportMissingImports]
from PIL import Image  # pyright: ignore[reportMissingImports]
import os
import fitz  # pyright: ignore[reportMissingImports]
import shutil
import uuid
import fitz  # pyright: ignore[reportMissingImports]
import zipfile
import pandas as pd  # pyright: ignore[reportMissingImports, reportMissingModuleSource]
import comtypes.client # pyright: ignore[reportMissingImports]
import pdfplumber  # pyright: ignore[reportMissingImports]
from pdf2docx import Converter  # pyright: ignore[reportMissingImports]
from docx2pdf import convert  # pyright: ignore[reportMissingImports]
from reportlab.lib.pagesizes import letter, landscape # pyright: ignore[reportMissingImports, reportMissingModuleSource]
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer # pyright: ignore[reportMissingImports, reportMissingModuleSource]
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle # pyright: ignore[reportMissingImports, reportMissingModuleSource]
from reportlab.lib import colors # pyright: ignore[reportMissingImports, reportMissingModuleSource]
from typing import Optional, List
from pptx import Presentation  # pyright: ignore[reportMissingImports]
from pptx.util import Inches  # pyright: ignore[reportMissingImports]
from PIL import ImageEnhance  # pyright: ignore[reportMissingImports]
from weasyprint import HTML  # pyright: ignore[reportMissingImports]
from deep_translator import GoogleTranslator  # pyright: ignore[reportMissingImports]
from utils.security import validate_file_size, validate_pdf_file, cleanup_file
from routers import payment



app = FastAPI(title="Cloud File Converter API")

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

MAX_FILE_SIZE = 20 * 1024 * 1024
PRO_MAX_FILE_SIZE = 100 * 1024 * 1024

@app.get("/")
def read_root():
    return {"status": "File Converter API is running!"}

# Include the payment router for handling mock payments and PayHere integration
app.include_router(payment.router, prefix="/api/payment", tags=["Payment & Mock Checkout"])


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
async def convert_image(file: UploadFile = File(...), target_format: str = Form(...)):
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        img = Image.open(input_path)
        target_ext = target_format.lower()
        if target_ext in ["jpeg", "jpg"]:
            img = img.convert("RGB")
            target_ext = "jpeg"
            
        output_filename = f"{file_id}_converted.{target_ext}"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        img.save(output_path, target_ext.upper())
        
        return FileResponse(output_path, media_type=f"image/{target_ext}", filename=f"converted_image.{target_ext}")
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)

# 2. PDF to Word Endpoint
@app.post("/convert/pdf-to-word")
async def convert_pdf_to_word(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    output_filename = f"{file_id}_converted.docx"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        cv = Converter(input_path)
        cv.convert(output_path, start=0, end=None)
        cv.close()
        
        return FileResponse(output_path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename="converted_document.docx")
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)

# 3. Word to PDF Endpoint
@app.post("/convert/word-to-pdf")
async def convert_word_to_pdf(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    output_filename = f"{file_id}_converted.pdf"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        # docx2pdf uses MS Word installed on Windows in the background
        convert(input_path, output_path)
        
        return FileResponse(output_path, media_type="application/pdf", filename="converted_document.pdf")
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)

# 4. Multiple Images to PDF Endpoint with Uniform Size (A4 Standard Canvas)
@app.post("/convert/images-to-pdf")
async def convert_images_to_pdf(files: list[UploadFile] = File(...)):
    file_id = str(uuid.uuid4())
    saved_image_paths = []
    total_size = 0
    
    try:
        for i, file in enumerate(files):
            contents = await file.read()
            total_size += len(contents)
            
            if total_size > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail="Total files size exceeds the 20MB limit!")
                
            input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{i}_{file.filename}")
            with open(input_path, "wb") as f:
                f.write(contents)
            saved_image_paths.append(input_path)
            
        processed_images = []
        # Standard A4 size proportions at good resolution (e.g., 1240 x 1754 pixels)
        target_width, target_height = 1240, 1754
        
        for path in saved_image_paths:
            img = Image.open(path)
            if img.mode != "RGB":
                img = img.convert("RGB")
                
            # 1. Create a blank white canvas of standard size
            canvas = Image.new("RGB", (target_width, target_height), (255, 255, 255))
            
            # 2. Resize image to fit inside the canvas while preserving aspect ratio
            img.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
            
            # 3. Calculate position to paste it right in the center of the canvas
            x = (target_width - img.width) // 2
            y = (target_height - img.height) // 2
            canvas.paste(img, (x, y))
            
            processed_images.append(canvas)
            
        if not processed_images:
            raise HTTPException(status_code=400, detail="No valid images provided")
            
        output_filename = f"{file_id}_converted.pdf"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        # Save all uniform images into a single PDF
        processed_images[0].save(
            output_path,
            "PDF",
            save_all=True,
            append_images=processed_images[1:]
        )
        
        return FileResponse(
            output_path, 
            media_type="application/pdf", 
            filename="merged_images.pdf"
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        for path in saved_image_paths:
            if os.path.exists(path):
                os.remove(path)
        if os.path.exists(output_path):
            os.remove(output_path)

# 5. Excel to PDF Endpoint
@app.post("/convert/excel-to-pdf")
async def convert_excel_to_pdf(file: UploadFile = File(...)):
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds the 20MB limit!")
        
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    output_filename = f"{file_id}_converted.pdf"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
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
        elements.append(Paragraph(f"Converted Report: {file.filename}", title_style))
        
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
        
        return FileResponse(
            output_path, 
            media_type="application/pdf", 
            filename="converted_spreadsheet.pdf"
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)
            if os.path.exists(output_path):
                os.remove(output_path)

# 6. PDF to Excel Endpoint
@app.post("/convert/pdf-to-excel")
async def convert_pdf_to_excel(file: UploadFile = File(...)):
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds the 20MB limit!")
        
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    output_filename = f"{file_id}_converted.xlsx"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
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
        
        return FileResponse(
            output_path, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
            filename="converted_table.xlsx"
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)
            if os.path.exists(output_path):
                os.remove(output_path)

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
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    
    with open(input_path, "wb") as f:
        f.write(contents)
        
    extracted_image_paths = []
    
    try:
        doc = fitz.open(input_path)
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
            
        doc.close()
        
        # If only 1 image extracted, return it directly
        if len(extracted_image_paths) == 1:
            return FileResponse(
                extracted_image_paths[0],
                media_type="image/png",
                filename=f"page_{target_page_indices[0] + 1}.png"
            )
            
        # If multiple images, bundle them into a ZIP file
        zip_filename = f"{file_id}_selected_images.zip"
        zip_path = os.path.join(OUTPUT_DIR, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for img_path in extracted_image_paths:
                zipf.write(img_path, arcname=os.path.basename(img_path))
                
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename="selected_pdf_images.zip"
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)
            for img_path in extracted_image_paths:
                if os.path.exists(img_path):
                    os.remove(img_path)

# 8. PowerPoint (.pptx) to PDF Endpoint (Windows MS Office required)
@app.post("/convert/pptx-to-pdf")
async def convert_pptx_to_pdf(file: UploadFile = File(...)):
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds the 20MB limit!")
        
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    output_filename = f"{file_id}_converted.pdf"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    with open(input_path, "wb") as f:
        f.write(contents)
        
    try:
        # Initialize PowerPoint COM object
        powerpoint = comtypes.client.CreateObject("Powerpoint.Application")
        powerpoint.Visible = 1
        
        # Open presentation and export as PDF (Format 32 = ppSaveAsPDF)
        deck = powerpoint.Presentations.Open(os.path.abspath(input_path))
        deck.SaveAs(os.path.abspath(output_path), 32)
        deck.Close()
        powerpoint.Quit()
        
        return FileResponse(
            output_path, 
            media_type="application/pdf", 
            filename="converted_presentation.pdf"
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PPT conversion error: {str(e)}")
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)
            if os.path.exists(output_path):
                os.remove(output_path)


# 9. PDF to PowerPoint (.pptx) Endpoint
@app.post("/convert/pdf-to-pptx")
async def convert_pdf_to_pptx(file: UploadFile = File(...)):
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds the 20MB limit!")
        
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    output_filename = f"{file_id}_converted.pptx"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    with open(input_path, "wb") as f:
        f.write(contents)
        
    try:
        doc = fitz.open(input_path)
        prs = Presentation()
        # Set slide dimensions to widescreen (16:9)
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
        
        blank_slide_layout = prs.slide_layouts[6] # Blank layout
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=150)
            
            img_path = os.path.join(UPLOAD_DIR, f"{file_id}_slide_{page_num}.png")
            pix.save(img_path)
            
            # Add slide and insert page image to fit the slide
            slide = prs.slides.add_slide(blank_slide_layout)
            slide.shapes.add_picture(img_path, 0, 0, width=prs.slide_width, height=prs.slide_height)
            
            # Cleanup temp image
            if os.path.exists(img_path):
                os.remove(img_path)
                if os.path.exists(output_path):
                    os.remove(output_path)
                
        doc.close()
        prs.save(output_path)
        
        return FileResponse(
            output_path, 
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation", 
            filename="converted_presentation.pptx"
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)
            if os.path.exists(output_path):
                os.remove(output_path)
                if os.path.exists(output_path):
                    os.remove(output_path)

# 10. Scan to PDF Endpoint (Enhanced for Scanned Document Look)
@app.post("/convert/scan-to-pdf")
async def convert_scan_to_pdf(
    files: list[UploadFile] = File(...),
    enhance: Optional[bool] = Form(True) # Option to boost contrast for text clarity
):
    file_id = str(uuid.uuid4())
    saved_image_paths = []
    total_size = 0
    
    try:
        for i, file in enumerate(files):
            contents = await file.read()
            total_size += len(contents)
            
            if total_size > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail="Total files size exceeds the 20MB limit!")
                
            input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{i}_{file.filename}")
            with open(input_path, "wb") as f:
                f.write(contents)
            saved_image_paths.append(input_path)
            
        processed_images = []
        target_width, target_height = 1240, 1754 # Standard A4 size
        
        for path in saved_image_paths:
            img = Image.open(path)
            if img.mode != "RGB":
                img = img.convert("RGB")
                
            # Enhance contrast if requested for scanned document clarity
            if enhance:
                # Enhance sharpness and contrast so text looks sharp like a real scanner
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(1.5)
                
                sharpness = ImageEnhance.Sharpness(img)
                img = sharpness.enhance(1.3)
                
            # Create A4 white canvas
            canvas = Image.new("RGB", (target_width, target_height), (255, 255, 255))
            
            # Resize image to fit canvas proportionally
            img.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
            
            # Center the image on canvas
            x = (target_width - img.width) // 2
            y = (target_height - img.height) // 2
            canvas.paste(img, (x, y))
            
            processed_images.append(canvas)
            
        if not processed_images:
            raise HTTPException(status_code=400, detail="No valid scanned images provided")
            
        output_filename = f"{file_id}_scanned.pdf"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        processed_images[0].save(
            output_path,
            "PDF",
            save_all=True,
            append_images=processed_images[1:]
        )
        
        return FileResponse(
            output_path, 
            media_type="application/pdf", 
            filename="scanned_document.pdf"
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        for path in saved_image_paths:
            if os.path.exists(path):
                os.remove(path)
                if os.path.exists(output_path):
                    os.remove(output_path)

# 11. HTML to PDF Endpoint (Using WeasyPrint)
@app.post("/convert/html-to-pdf")
async def convert_html_to_pdf(file: UploadFile = File(...)):
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds the 20MB limit!")
        
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    output_filename = f"{file_id}_converted.pdf"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    with open(input_path, "wb") as f:
        f.write(contents)
        
    try:
        # Convert HTML file directly to PDF using WeasyPrint
        HTML(input_path).write_pdf(output_path)
        
        return FileResponse(
            output_path, 
            media_type="application/pdf", 
            filename="converted_webpage.pdf"
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"HTML conversion error: {str(e)}")
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)
            if os.path.exists(output_path):
                os.remove(output_path)

#12. PDF Translation Endpoint (Sinhala, Tamil, English)
@app.post("/convert/pdf-translate")
async def pdf_translate(
    file: UploadFile = File(...),
    source_lang: str = Form(...), # e.g., 'si', 'ta', 'en'
    target_lang: str = Form(...)  # e.g., 'en', 'si', 'ta'
):
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds the 20MB limit!")
        
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    output_filename = f"{file_id}_translated.pdf"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
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
        
        # 2. Translate text using deep-translator
        # Language codes: 'si' (Sinhala), 'ta' (Tamil), 'en' (English)
        translator = GoogleTranslator(source=source_lang, target=target_lang)
        
        # Google translator has character limits per request (~5000 chars), let's chunk if necessary
        # For simplicity in this demo, let's translate paragraph by paragraph or chunked
        chunks = [full_text[i:i+4500] for i in range(0, len(full_text), 4500)]
        translated_chunks = []
        
        for chunk in chunks:
            translated_text = translator.translate(chunk)
            translated_chunks.append(translated_text)
            
        final_translated_text = "\n\n".join(translated_chunks)
        
        # 3. Generate a clean new PDF with the translated text using ReportLab
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
            spaceAfter=10
        )
        
        elements.append(Paragraph(f"Translated Document ({source_lang.upper()} ➔ {target_lang.upper()})", title_style))
        elements.append(Spacer(1, 10))
        
        for paragraph in final_translated_text.split("\n"):
            if paragraph.strip():
                elements.append(Paragraph(paragraph.strip(), body_style))
                
        doc.build(elements)
        
        return FileResponse(
            output_path, 
            media_type="application/pdf", 
            filename=f"translated_{source_lang}_to_{target_lang}.pdf"
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Translation error: {str(e)}")
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)
            if os.path.exists(output_path):
                os.remove(output_path)

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
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    output_filename = f"{file_id}_organized.pdf"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    with open(input_path, "wb") as f:
        f.write(contents)
        
    try:
        doc = fitz.open(input_path)
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
        doc.close()
        
        return FileResponse(
            output_path, 
            media_type="application/pdf", 
            filename="organized_document.pdf"
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Organize PDF error: {str(e)}")
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)
            if os.path.exists(output_path):
                os.remove(output_path)

@app.post("/convert/merge-pdfs")
async def merge_pdfs(files: list[UploadFile] = File(...)):
    file_id = str(uuid.uuid4())
    saved_paths = []
    total_size = 0
    
    try:
        # Create an empty master PDF document for merging
        merged_doc = fitz.open()
        
        for i, file in enumerate(files):
            contents = await file.read()
            total_size += len(contents)
            
            if total_size > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail="Total files size exceeds the 20MB limit!")
                
            input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{i}_{file.filename}")
            with open(input_path, "wb") as f:
                f.write(contents)
            saved_paths.append(input_path)
            
            # Open each PDF and append its pages to the master merged document
            with fitz.open(input_path) as doc:
                merged_doc.insert_pdf(doc)
                
        output_filename = f"{file_id}_merged.pdf"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        merged_doc.save(output_path)
        merged_doc.close()
        
        return FileResponse(
            output_path, 
            media_type="application/pdf", 
            filename="merged_document.pdf"
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Merge PDFs error: {str(e)}")
    finally:
        # Cleanup temporary input files
        for path in saved_paths:
            if os.path.exists(path):
                os.remove(path)
                if os.path.exists(output_path):
                    os.remove(output_path)

# 14. Split PDF into Multiple Parts Endpoint (With Download Links)
@app.post("/convert/split-pdf-links")
async def split_pdf_links(
    file: UploadFile = File(...),
    split_ranges: str = Form(...)  # e.g., "1-3, 4-6" or individual pages
):
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Total files size exceeds the 20MB limit!")
        
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    
    with open(input_path, "wb") as f:
        f.write(contents)
        
    response_links = []
    split_pdf_paths = []
    
    try:
        doc = fitz.open(input_path)
        total_pages = len(doc)
        
        # Parse ranges like "1-3, 4-5" or comma-separated numbers
        ranges = [r.strip() for r in split_ranges.split(",")]
        
        for i, rng in enumerate(ranges):
            sub_doc = fitz.open()
            
            if "-" in rng:
                start_p, end_p = map(int, rng.split("-"))
                start_idx = max(0, start_p - 1)
                end_idx = min(total_pages - 1, end_p - 1)
                sub_doc.insert_pdf(doc, from_page=start_idx, to_page=end_idx)
                part_name = f"Part_{i+1}_Pages_{start_p}_to_{end_p}.pdf"
            else:
                p_num = int(rng)
                idx = p_num - 1
                if 0 <= idx < total_pages:
                    sub_doc.insert_pdf(doc, from_page=idx, to_page=idx)
                    part_name = f"Part_{i+1}_Page_{p_num}.pdf"
                else:
                    continue
                    
            part_filename = f"{file_id}_{part_name}"
            part_path = os.path.join(OUTPUT_DIR, part_filename)
            sub_doc.save(part_path)
            sub_doc.close()
            split_pdf_paths.append((part_path, part_name))
            
            # Add individual download URL
            response_links.append({
                "title": f"Part {i+1} ({rng})",
                "filename": part_name,
                "url": f"http://localhost:8000/download-file/{part_filename}"
            })
            
        doc.close()
        
        if not response_links:
            raise HTTPException(status_code=400, detail="Invalid split ranges provided!")
            
        # Optional: Bundle all into a ZIP file for a "Download All" option if needed
        zip_filename = f"{file_id}_all_parts.zip"
        zip_path = os.path.join(OUTPUT_DIR, zip_filename)
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for path, name in split_pdf_paths:
                zipf.write(path, arcname=name)
                
        all_download_url = f"http://localhost:8000/download-file/{zip_filename}"
        
        return {
            "status": "success", 
            "parts": response_links,
            "download_all_url": all_download_url
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)
            if os.path.exists(zip_path):
                os.remove(zip_path)

# Serve individual or zip generated files
@app.get("/download-file/{filename}")
async def download_file(filename: str):
    file_path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(file_path):
        # Clean up internal uuid prefix for the actual downloaded filename
        clean_name = filename.split("_", 1)[1] if "_" in filename else filename
        return FileResponse(file_path, filename=clean_name)
    raise HTTPException(status_code=404, detail="File not found")
