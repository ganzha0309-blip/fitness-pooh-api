import os
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore
from telegram import Bot
from telegram._utils.warnings import warn as tg_warn
import warnings
import tempfile

# Загрузка Firebase ключа
firebase_key_json = os.getenv("FIREBASE_KEY")
if firebase_key_json:
    # Создаем временный файл из содержимого переменной
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write(firebase_key_json)
        firebase_key_path = f.name
    print(f"Using temporary Firebase key file: {firebase_key_path}")
else:
    firebase_key_path = os.getenv("FIREBASE_KEY_PATH", "fitnesspooh-firebase-key.json")
    print(f"Using local Firebase key file: {firebase_key_path}")

cred = credentials.Certificate(firebase_key_path)
firebase_admin.initialize_app(cred)
db = firestore.client()

# Ignore telegram warning about webhook (we don't use it)
warnings.filterwarnings("ignore", category=UserWarning, module="telegram")

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set")

FIREBASE_KEY_PATH = os.getenv("FIREBASE_KEY_PATH", "fitnesspooh-firebase-key.json")

# Initialize Firebase
cred = credentials.Certificate(FIREBASE_KEY_PATH)
firebase_admin.initialize_app(cred)
db = firestore.client()

# Initialize Telegram Bot (only for validation)
bot = Bot(token=BOT_TOKEN)

app = FastAPI(title="Fitness Pooh API")

# Allow CORS for your frontend domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ganzha0309-blip.github.io",
        "http://localhost:5173",
        "https://fitness-pooh-app.netlify.app",  # если перейдёшь на Netlify
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Pydantic models ----------
class AuthRequest(BaseModel):
    initData: str

class HabitRequest(BaseModel):
    initData: str
    habit: str  # "water", "workout", "sleep"

class ProfileResponse(BaseModel):
    name: str
    xp: int
    streak: int
    subscription: str
    username: Optional[str]
    last_action_date: Optional[str]
    level: str  # вычисляем

# ---------- Helper functions ----------
def compute_level(xp: int) -> str:
    levels = {
        0: "🍯 Новобранец",
        100: "💪 Боец",
        200: "🚗 Машина",
        300: "🐻 Медведь",
        400: "🔥 Режим зверя",
        500: "👑 Легенда"
    }
    for threshold in sorted(levels.keys(), reverse=True):
        if xp >= threshold:
            return levels[threshold]
    return levels[0]

def verify_init_data(init_data: str) -> dict:
    """Проверяет подпись initData и возвращает данные пользователя"""
    try:
        # Используем стандартную функцию telegram.Bot
        result = bot.parse_web_app_data(init_data)
        # result – объект, у него есть атрибут user
        if not result.user:
            raise ValueError("No user in initData")
        return {
            "id": result.user.id,
            "first_name": result.user.first_name,
            "username": result.user.username,
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid initData: {e}")

def get_or_create_user(telegram_id: str, first_name: str, username: str = None):
    user_ref = db.collection('users').document(telegram_id)
    doc = user_ref.get()
    if doc.exists:
        return doc.to_dict()
    else:
        # Create new user
        new_user = {
            "name": first_name,
            "username": username or "",
            "xp": 0,
            "streak": 0,
            "last_action_date": None,
            "subscription": "free",
            "habits": {"water": 0, "workout": 0, "sleep": 0},
        }
        user_ref.set(new_user)
        return new_user

# ---------- API endpoints ----------
@app.post("/auth", response_model=ProfileResponse)
async def auth(request: AuthRequest):
    data = verify_init_data(request.initData)
    user = get_or_create_user(str(data["id"]), data["first_name"], data.get("username"))
    return ProfileResponse(
        name=user["name"],
        xp=user["xp"],
        streak=user["streak"],
        subscription=user["subscription"],
        username=user.get("username"),
        last_action_date=user.get("last_action_date"),
        level=compute_level(user["xp"])
    )

@app.post("/habit")
async def mark_habit(request: HabitRequest):
    data = verify_init_data(request.initData)
    telegram_id = str(data["id"])
    habit = request.habit
    if habit not in ["water", "workout", "sleep"]:
        raise HTTPException(status_code=400, detail="Invalid habit")

    today = datetime.now(timezone.utc).date().isoformat()
    user_ref = db.collection('users').document(telegram_id)
    doc = user_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="User not found")

    user = doc.to_dict()
    habits = user.get("habits", {})
    last_date = user.get("last_action_date")

    # Reset habits if new day
    if last_date != today:
        habits = {"water": 0, "workout": 0, "sleep": 0}
        # Update streak
        if last_date:
            last = datetime.fromisoformat(last_date).date()
            today_dt = datetime.now(timezone.utc).date()
            if (today_dt - last).days == 1:
                streak = user.get("streak", 0) + 1
            else:
                streak = 1
        else:
            streak = 1
    else:
        streak = user.get("streak", 0)

    if habits.get(habit, 0) >= 1:
        return {"ok": False, "message": "Already marked today"}

    # Mark habit
    habits[habit] = 1
    new_xp = user.get("xp", 0) + 10

    user_ref.update({
        "xp": new_xp,
        "streak": streak,
        "last_action_date": today,
        "habits": habits,
    })

    new_level = compute_level(new_xp)
    return {
        "ok": True,
        "new_xp": new_xp,
        "new_streak": streak,
        "level": new_level,
        "message": f"+10 XP! Streak: {streak} days"
    }

@app.get("/trainings")
async def get_trainings(initData: str):
    # Сейчас просто заглушка, позже добавим чтение из Firestore
    return [
        {"id": 1, "name": "Утренняя зарядка", "level": "free"},
        {"id": 2, "name": "Разминка для спины", "level": "free"},
        {"id": 3, "name": "Интенсив на пресс", "level": "base"},
    ]

@app.get("/health")
async def health():
    return {"status": "ok"}