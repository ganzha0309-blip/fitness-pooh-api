import hashlib
import hmac
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qs, unquote

import firebase_admin
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from firebase_admin import credentials, firestore
from pydantic import BaseModel


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set")

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
firebase_admin.initialize_app(cred)
db = firestore.client()

MSK = timezone(timedelta(hours=3))
HABITS = {"water", "workout", "sleep"}
LEVELS = {
    0: "🍯 Новобранец",
    100: "💪 Боец",
    200: "🚗 Машина",
    300: "🐻 Медведь",
    400: "🔥 Режим зверя",
    500: "👑 Легенда",
}

app = FastAPI(title="Fitness Pooh API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ganzha0309-blip.github.io",
        "https://ganzha0309-blip.github.io/fitness-pooh-app",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://fitness-pooh-app.netlify.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthRequest(BaseModel):
    initData: str


class HabitRequest(BaseModel):
    initData: str
    habit: str


class ProfileResponse(BaseModel):
    name: str
    xp: int
    streak: int
    subscription: str
    subscription_until: Optional[str] = None
    username: Optional[str] = None
    last_action_date: Optional[str] = None
    level: str
    habits: dict[str, int]


def today_iso() -> str:
    return datetime.now(MSK).date().isoformat()


def compute_level(xp: int) -> str:
    for threshold in sorted(LEVELS.keys(), reverse=True):
        if xp >= threshold:
            return LEVELS[threshold]
    return LEVELS[0]


def verify_init_data(init_data: str) -> dict:
    parsed = parse_qs(init_data)
    if "hash" not in parsed:
        raise HTTPException(status_code=401, detail="No hash in initData")

    received_hash = parsed["hash"][0]
    del parsed["hash"]

    check_string = "\n".join(
        f"{key}={unquote(parsed[key][0])}" for key in sorted(parsed.keys())
    )
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid hash")

    user_str = parsed.get("user", [None])[0]
    if not user_str:
        raise HTTPException(status_code=401, detail="No user in initData")

    user = json.loads(unquote(user_str))
    return {
        "id": user.get("id"),
        "first_name": user.get("first_name", ""),
        "username": user.get("username", ""),
    }


def get_or_create_user(telegram_id: str, first_name: str, username: str | None = None):
    user_ref = db.collection("users").document(telegram_id)
    doc = user_ref.get()
    if doc.exists:
        user = doc.to_dict()
        updates = {}
        if user.get("username") != (username or ""):
            updates["username"] = username or ""
        if first_name and user.get("name") != first_name:
            updates["name"] = first_name
        if "subscription_until" not in user:
            updates["subscription_until"] = None
        if updates:
            user_ref.update(updates)
            user.update(updates)
        return user

    new_user = {
        "name": first_name,
        "username": username or "",
        "xp": 0,
        "streak": 0,
        "last_action_date": None,
        "subscription": "free",
        "subscription_until": None,
        "habits": {"water": 0, "workout": 0, "sleep": 0},
        "created_at": today_iso(),
    }
    user_ref.set(new_user)
    return new_user


def today_habits(user: dict) -> dict[str, int]:
    if user.get("last_action_date") != today_iso():
        return {"water": 0, "workout": 0, "sleep": 0}
    habits = user.get("habits", {})
    return {
        "water": int(bool(habits.get("water"))),
        "workout": int(bool(habits.get("workout"))),
        "sleep": int(bool(habits.get("sleep"))),
    }


@app.post("/auth", response_model=ProfileResponse)
async def auth(request: AuthRequest):
    data = verify_init_data(request.initData)
    user = get_or_create_user(str(data["id"]), data["first_name"], data.get("username"))
    return ProfileResponse(
        name=user["name"],
        xp=user.get("xp", 0),
        streak=user.get("streak", 0),
        subscription=user.get("subscription", "free"),
        subscription_until=user.get("subscription_until"),
        username=user.get("username"),
        last_action_date=user.get("last_action_date"),
        level=compute_level(user.get("xp", 0)),
        habits=today_habits(user),
    )


@app.post("/habit")
async def mark_habit(request: HabitRequest):
    data = verify_init_data(request.initData)
    telegram_id = str(data["id"])
    habit = request.habit
    if habit not in HABITS:
        raise HTTPException(status_code=400, detail="Invalid habit")

    today = today_iso()
    user_ref = db.collection("users").document(telegram_id)
    doc = user_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="User not found")

    user = doc.to_dict()
    habits = user.get("habits", {})
    last_date = user.get("last_action_date")

    if last_date != today:
        habits = {"water": 0, "workout": 0, "sleep": 0}
        try:
            previous_date = datetime.fromisoformat(last_date).date() if last_date else None
        except ValueError:
            previous_date = None

        if previous_date and (datetime.now(MSK).date() - previous_date).days == 1:
            streak = user.get("streak", 0) + 1
        else:
            streak = 1
    else:
        streak = user.get("streak", 0)

    if habits.get(habit, 0) >= 1:
        return {
            "ok": False,
            "message": "Эта привычка уже отмечена сегодня.",
            "xp": user.get("xp", 0),
            "streak": streak,
            "level": compute_level(user.get("xp", 0)),
            "habits": today_habits({"last_action_date": today, "habits": habits}),
        }

    habits[habit] = 1
    new_xp = user.get("xp", 0) + 10

    user_ref.update(
        {
            "xp": new_xp,
            "streak": streak,
            "last_action_date": today,
            "habits": habits,
        }
    )

    return {
        "ok": True,
        "new_xp": new_xp,
        "new_streak": streak,
        "level": compute_level(new_xp),
        "habits": today_habits({"last_action_date": today, "habits": habits}),
        "message": f"+10 XP! Серия: {streak} дн.",
    }


@app.get("/trainings")
async def get_trainings():
    return [
        {
            "id": "morning",
            "title": "Утренняя зарядка",
            "description": "Мягкий запуск дня: суставы, дыхание, легкий тонус.",
            "subscription": "free",
            "category": "Дом",
            "duration": "10 мин",
        },
        {
            "id": "back-warmup",
            "title": "Разминка для спины",
            "description": "Снимает зажимы после сидячего дня и готовит к тренировке.",
            "subscription": "free",
            "category": "Мобилити",
            "duration": "12 мин",
        },
        {
            "id": "press-base",
            "title": "Интенсив на пресс",
            "description": "Короткая тренировка корпуса для Base-подписки.",
            "subscription": "base",
            "category": "Кор",
            "duration": "18 мин",
        },
        {
            "id": "mass-a",
            "title": "Массонабор: тренировка А",
            "description": "Базовая силовая схема для прогресса в объеме.",
            "subscription": "pro",
            "category": "Зал",
            "duration": "55 мин",
        },
        {
            "id": "vip-plan",
            "title": "Личная схема от Пуха",
            "description": "VIP-программа под цель, график и восстановление.",
            "subscription": "vip",
            "category": "Персонально",
            "duration": "Индивидуально",
        },
    ]


@app.get("/health")
async def health():
    return {"status": "ok"}
