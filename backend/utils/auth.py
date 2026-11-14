import firebase_admin # pyright: ignore[reportMissingImports]
from firebase_admin import credentials, auth # pyright: ignore[reportMissingImports]
from fastapi import HTTPException, Security, Optional # pyright: ignore[reportMissingImports]
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials # pyright: ignore[reportMissingImports]

# Firebase Admin SDK Initialization
# (ඔයාගේ backend ෆෝල්ඩර් එකේ firebase_secret.json තියෙන්න ඕනේ)
cred = credentials.Certificate("backend/firebase_secret.json")
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

security = HTTPBearer(auto_error=False)

def verify_firebase_token(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> Optional[dict]:
    """
    Frontend එකෙන් එවන Firebase ID Token එක verify කරයි.
    ටෝකන් එකක් නැත්නම් None ලබා දෙයි (අපිට 25MB ට අඩු files වලට ලොගින් වීම අනිවාර්ය නොකර තබා ගැනීමට).
    """
    if not credentials:
        return None
    
    token = credentials.credentials
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token  # මෙතුළ uid, email වැනි විස්තර අඩංගු වේ
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid authentication token: {str(e)}"
        )