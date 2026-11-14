from typing import Optional
from firebase_admin import auth  # pyright: ignore[reportMissingImports]
from fastapi import HTTPException, Security  # pyright: ignore[reportMissingImports]
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials  # pyright: ignore[reportMissingImports]

# Firebase Admin SDK එක initialize වෙන්නේ database.py එකේදී (FIREBASE_CREDENTIALS_PATH .env එකෙන්).
# මෙතන import කරන්නේ ඒක කලින් initialize වෙලා තියෙනවා කියලා විශ්වාස කරගන්න විතරයි.
import database  # noqa: F401  # pyright: ignore[reportUnusedImport]

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
