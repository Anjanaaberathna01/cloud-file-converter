from fastapi import APIRouter, Form, HTTPException  # pyright: ignore[reportMissingImports]
import os
from dotenv import load_dotenv  # pyright: ignore[reportMissingImports]
from database import db

load_dotenv()

router = APIRouter()

# Mock / Placeholder IDs (Real keys පස්සේ දාගන්න පුළුවන්)
PAYHERE_MERCHANT_ID = os.getenv("PAYHERE_MERCHANT_ID", "TEST_MERCHANT_ID")
PAYHERE_MERCHANT_SECRET = os.getenv("PAYHERE_MERCHANT_SECRET", "TEST_SECRET")

@router.post("/create-checkout")
async def create_mock_checkout(
    user_id: str = Form(...),
    amount: float = Form(25.00)
):
    """
    Mock Checkout Endpoint: 
    Local testing සඳහා PayHere checkout request එක simulate කරයි.
    """
    # මෙතැනදී frontend එකට PayHere redirect url එක හෝ testing sandbox URL එක යවන්න පුළුවන්
    mock_order_id = f"ORDER_{user_id}_{int(os.urandom(4).hex(), 16)}"
    
    return {
        "status": "success",
        "order_id": mock_order_id,
        "amount": amount,
        "currency": "LKR",
        "checkout_url": f"http://localhost:8000/api/payment/mock-success-page?order_id={mock_order_id}&user_id={user_id}"
    }

@router.get("/mock-success-page")
async def mock_success_page(order_id: str, user_id: str):
    """
    Local testing සඳහා payment එක successful බව simulate කරමින් 
    database එකේ user ට token එකක් එකතු කරන test route එකක්.
    """
    try:
        if user_id:
            user_ref = db.collection("users").document(user_id)
            user_doc = user_ref.get()
            if user_doc.exists:
                current_tokens = user_doc.to_dict().get("paid_tokens", 0)
                user_ref.update({"paid_tokens": current_tokens + 1})
            else:
                user_ref.set({"paid_tokens": 1}, merge=True)
                
        return {
            "status": "success",
            "message": f"🎉 Mock Payment Successful for Order: {order_id}! Now you can convert your file."
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/payhere-webhook")
async def payhere_webhook(
    merchant_id: str = Form(...),
    order_id: str = Form(...),
    payhere_amount: str = Form(...),
    payhere_currency: str = Form(...),
    status_code: str = Form(...),
    md5sig: str = Form(...),
    custom_field: str = Form(None)
):
    # Production එකට මාරු වුණාම පාවිච්චි කරන Real Webhook logic එක මෙතැන තියෙනවා
    if status_code == "2":
        return {"status": "success", "message": "Production payment verified."}
    return {"status": "pending"}