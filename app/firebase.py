import os
import tempfile

import firebase_admin
from firebase_admin import credentials, firestore

from app.config import BOT_TOKEN  # noqa: F401 - ensures env is loaded and validated.


firebase_key_json = os.getenv("FIREBASE_KEY")
if firebase_key_json:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(firebase_key_json)
        firebase_key_path = f.name
    print(f"Using temporary Firebase key file: {firebase_key_path}")
else:
    firebase_key_path = os.getenv("FIREBASE_KEY_PATH", "fitnesspooh-firebase-key.json")
    print(f"Using local Firebase key file: {firebase_key_path}")

cred = credentials.Certificate(firebase_key_path)
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()
