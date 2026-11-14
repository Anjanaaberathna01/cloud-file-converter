import firebase_admin  # pyright: ignore[reportMissingImports]
from firebase_admin import credentials, firestore  # pyright: ignore[reportMissingImports]
import os
from dotenv import load_dotenv  # pyright: ignore[reportMissingImports]

# .env file එක load කරගැනීම
load_dotenv()

# Firebase credentials path එක .env එකෙන් හෝ default විදිහට ලබා ගැනීම
cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase_secret.json")

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print(" Firebase Connected Successfully!")
    except Exception as e:
        print(f" Firebase Connection Error: {e}")

# Firestore database instance එක (Users ලාගේ Pro status සහ history save කිරීමට)
db = firestore.client()