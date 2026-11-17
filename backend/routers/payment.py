from fastapi import APIRouter, Form, HTTPException, Depends
import os
from dotenv import load_dotenv
from database import db
from utils.auth import verify_firebase_token
from datetime import datetime, timedelta

load_dotenv()

router = APIRouter()

@router.post("/create-checkout")
async def create_checkout(
    package_type: str = Form(...),  # "micro" (Rs. 25) හෝ "pro" (Rs. 2500)
    user: dict = Depends(verify_firebase_token)
):
    
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required for payments.")

    user_id = user.get("uid")
    user_email = user.get("email")

    if package_type == "micro":
        amount = 25.00
        description = "Single Large File Conversion (Micro-payment)"
    elif package_type == "pro":
        amount = 2500.00
        description = "Monthly Pro Package Subscription"
    else:
        raise HTTPException(status_code=400, detail="Invalid package type specified!")

    # Unique Order ID එකක් සෑදීම
    order_id = f"ORD_{user_id}_{int(datetime.now().timestamp())}"

    # මෙතැනදී PayHere හෝ Stripe සැබෑ Checkout URL එක සම්බන්ධ කළ යුතුය.
    # දැනට Testing සඳහා Mock/Sandbox URL එකක් ලබා දෙයි:
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
    """
    ගෙවීම සාර්ථක වූ පසු (Payment Gateway එකෙන් පසු) 
    Firebase Firestore හි යූසර්ගේ පැකේජ් ස්ටේටස් එක අප්ඩේට් කරයි.
    """
    try:
        user_ref = db.collection("users").document(user_id)
        
        if package_type == "pro":
            # මාසයකට (දින 30කට) Pro සක්‍රීය කිරීම
            expiry_date = datetime.now() + timedelta(days=30)
            user_ref.set({
                "is_pro": True,
                "pro_expiry_date": expiry_date,
                "last_payment_date": datetime.now()
            }, merge=True)
            message = "🎉 Pro Package (Rs. 2500/month) Activated Successfully!"
            
        elif package_type == "micro":
            # 25MB ට වැඩි එක් ගොනුවක් සඳහා ගෙවීම සාර්ථක වූ බව සටහන් කිරීම
            user_ref.set({
                "has_paid_micro_fee": True
            }, merge=True)
            message = "🎉 Micro-payment (Rs. 25) Successful! You can now convert your file."

        return {
            "status": "success",
            "message": f"{message} (Order: {order_id})"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))