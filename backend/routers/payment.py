from fastapi import APIRouter, Form, HTTPException, Depends
import os
from dotenv import load_dotenv
from database import db
from utils.auth import verify_firebase_token
from datetime import datetime, timedelta
from typing import Optional

load_dotenv()

router = APIRouter()

@router.post("/create-checkout")
async def create_checkout(
    package_type: str = Form(...),  # "micro" හෝ "pro"
    user_id: Optional[str] = Form("test_user_123") # ටෙස්ට් කිරීමට ඩිෆෝල්ට් යූසර් කෙනෙක් දීම
):
    """
    Mock Checkout Endpoint: 
    Local testing සඳහා authentication නැතුව වැඩ කිරීමට සකස් කළ හැක.
    """
    if package_type == "micro":
        amount = 25.00
    elif package_type == "pro":
        amount = 2500.00
    else:
        raise HTTPException(status_code=400, detail="Invalid package type specified!")

    order_id = f"ORD_{user_id}_{int(datetime.now().timestamp())}"
    
    # Mock checkout URL එක
    checkout_url = f"http://localhost:8000/api/payment/mock-success-page?order_id={order_id}&user_id={user_id}&package_type={package_type}"

    return {
        "status": "success",
        "order_id": order_id,
        "amount": amount,
        "currency": "LKR",
        "checkout_url": checkout_url
    }

@router.get("/mock-success-page")
async def mock_success_page(order_id: str, user_id: str, package_type: str):
    
    try:
        # ඩේටාබේස් එකට ලිවීම තාවකාලිකව අත්හිටුවා ඇත (Test කිරීමට පමණි)
        # user_ref = db.collection("users").document(user_id)
        # ...
        
        return {
            "status": "success",
            "message": f"Mock Payment Successful for Order: {order_id} ({package_type.upper()})! Now you can convert your file."
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}