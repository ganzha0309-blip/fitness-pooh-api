import hashlib
import hmac
import json
import os
import tempfile
import time
import uuid
from datetime import date, datetime, timedelta, timezone
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
DEFAULT_HABITS = [
    {"code": "water", "title": "Вода", "icon": "💧", "caption": "2 литра за день", "is_default": True},
    {"code": "workout", "title": "Тренировка", "icon": "🏋️", "caption": "Любая активность", "is_default": True},
    {"code": "sleep", "title": "Сон", "icon": "😴", "caption": "7-8 часов", "is_default": True},
]
CUSTOM_HABIT_LIMITS = {"free": 0, "base": 1, "pro": 2, "vip": 3}
SUBSCRIPTION_ORDER = {"free": 0, "base": 1, "pro": 2, "vip": 3}
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
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthRequest(BaseModel):
    initData: str


class HabitRequest(BaseModel):
    initData: str
    habit: str


class HabitEditRequest(BaseModel):
    initData: str
    code: str
    title: str
    icon: Optional[str] = None
    caption: Optional[str] = None


class HabitAddRequest(BaseModel):
    initData: str
    title: str
    icon: Optional[str] = None
    caption: Optional[str] = None


class HabitDeleteRequest(BaseModel):
    initData: str
    code: str


class ProgressAddRequest(BaseModel):
    initData: str
    weight: Optional[float] = None
    waist: Optional[float] = None
    chest: Optional[float] = None
    arm: Optional[float] = None
    thigh: Optional[float] = None
    note: Optional[str] = None


class ProgressDeleteRequest(BaseModel):
    initData: str
    entry_id: str


class ChallengeActionRequest(BaseModel):
    initData: str
    challenge_id: str


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
    habit_items: list[dict]
    custom_habit_limit: int
    custom_habit_count: int


def today_iso() -> str:
    return datetime.now(MSK).date().isoformat()


def now_iso() -> str:
    return datetime.now(MSK).isoformat(timespec="milliseconds")


def compute_level(xp: int) -> str:
    for threshold in sorted(LEVELS.keys(), reverse=True):
        if xp >= threshold:
            return LEVELS[threshold]
    return LEVELS[0]


def normalize_subscription(subscription: str | None) -> str:
    value = (subscription or "free").lower()
    return value if value in CUSTOM_HABIT_LIMITS else "free"


def effective_subscription(user: dict) -> str:
    subscription = normalize_subscription(user.get("subscription"))
    until = user.get("subscription_until")
    if subscription == "free" or not until:
        return subscription
    if isinstance(until, datetime):
        until_date = until.date()
    elif isinstance(until, date):
        until_date = until
    else:
        try:
            until_date = datetime.fromisoformat(str(until)).date()
        except (TypeError, ValueError):
            return "free"
    if until_date < datetime.now(MSK).date():
        return "free"
    return subscription


def can_access(user_sub: str, required_sub: str) -> bool:
    return SUBSCRIPTION_ORDER.get(normalize_subscription(user_sub), 0) >= SUBSCRIPTION_ORDER.get(
        normalize_subscription(required_sub), 0
    )


def participant_doc_id(user_id: str, challenge_id: str) -> str:
    return f"{user_id}_{challenge_id}"


def normalize_icon(icon: str | None, fallback: str = "✅") -> str:
    value = (icon or "").strip()
    return value[:4] if value else fallback


def normalize_caption(caption: str | None) -> str:
    return (caption or "").strip()[:48]


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
        if "habit_settings" not in user:
            updates["habit_settings"] = {}
        if "custom_habits" not in user:
            updates["custom_habits"] = []
        if "progress_entries" not in user:
            updates["progress_entries"] = []
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
        "habits": {habit["code"]: 0 for habit in DEFAULT_HABITS},
        "habit_settings": {},
        "custom_habits": [],
        "progress_entries": [],
        "created_at": today_iso(),
    }
    user_ref.set(new_user)
    return new_user


def get_habit_items(user: dict) -> list[dict]:
    settings = user.get("habit_settings", {}) or {}
    items = []
    for habit in DEFAULT_HABITS:
        custom = settings.get(habit["code"], {})
        items.append(
            {
                **habit,
                "title": custom.get("title") or habit["title"],
                "icon": custom.get("icon") or habit["icon"],
                "caption": custom.get("caption") or "",
            }
        )

    subscription = effective_subscription(user)
    custom_limit = CUSTOM_HABIT_LIMITS[subscription]
    for habit in (user.get("custom_habits") or [])[:custom_limit]:
        code = habit.get("code")
        title = (habit.get("title") or "").strip()
        if code and title:
            items.append(
                {
                    "code": code,
                    "title": title[:32],
                    "icon": normalize_icon(habit.get("icon")),
                    "caption": habit.get("caption") or "",
                    "is_default": False,
                }
            )
    return items


def empty_habits_for(user: dict) -> dict[str, int]:
    return {habit["code"]: 0 for habit in get_habit_items(user)}


def today_habits(user: dict) -> dict[str, int]:
    empty = empty_habits_for(user)
    if user.get("last_action_date") != today_iso():
        return empty
    stored = user.get("habits", {}) or {}
    return {code: int(bool(stored.get(code))) for code in empty}


def profile_payload(user: dict) -> ProfileResponse:
    subscription = effective_subscription(user)
    custom_habits = user.get("custom_habits") or []
    return ProfileResponse(
        name=user["name"],
        xp=user.get("xp", 0),
        streak=user.get("streak", 0),
        subscription=subscription,
        subscription_until=user.get("subscription_until"),
        username=user.get("username"),
        last_action_date=user.get("last_action_date"),
        level=compute_level(user.get("xp", 0)),
        habits=today_habits(user),
        habit_items=get_habit_items(user),
        custom_habit_limit=CUSTOM_HABIT_LIMITS[subscription],
        custom_habit_count=len(custom_habits),
    )


def current_user_from_init(init_data: str) -> tuple[str, dict]:
    data = verify_init_data(init_data)
    telegram_id = str(data["id"])
    user = get_or_create_user(telegram_id, data["first_name"], data.get("username"))
    return telegram_id, user


def clean_measure(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if value <= 0 or value > 500:
        raise HTTPException(status_code=400, detail="Invalid measurement value")
    return round(float(value), 1)


def progress_payload(user: dict) -> dict:
    entries = user.get("progress_entries") or []
    entries = sorted(
        entries,
        key=lambda item: item.get("created_at") or item.get("date", "") or "",
        reverse=True,
    )
    latest = entries[0] if entries else None
    previous = entries[1] if len(entries) > 1 else None
    changes = {}
    if latest and previous:
        for key in ("weight", "waist", "chest", "arm", "thigh"):
            if latest.get(key) is not None and previous.get(key) is not None:
                changes[key] = round(latest[key] - previous[key], 1)
    return {"entries": entries[:50], "latest": latest, "changes": changes}


def challenge_payload(challenge_id: str, challenge: dict, user_id: str, user: dict) -> dict:
    subscription = effective_subscription(user)
    required_subscription = normalize_subscription(challenge.get("required_subscription"))
    participant_ref = db.collection("challenge_participants").document(
        participant_doc_id(user_id, challenge_id)
    )
    participant_doc = participant_ref.get()
    participant = participant_doc.to_dict() if participant_doc.exists else None
    completed_dates = participant.get("completed_dates", []) if participant else []
    duration_days = int(challenge.get("duration_days") or 7)
    return {
        "id": challenge_id,
        "title": challenge.get("title", "Challenge"),
        "description": challenge.get("description", ""),
        "duration_days": duration_days,
        "reward_xp": int(challenge.get("reward_xp") or 0),
        "required_subscription": required_subscription,
        "status": challenge.get("status", "active"),
        "participants_count": int(challenge.get("participants_count") or 0),
        "available": can_access(subscription, required_subscription),
        "joined": participant is not None,
        "participant_status": participant.get("status", "none") if participant else "none",
        "progress_days": len(completed_dates),
        "completed_dates": completed_dates,
        "done_today": today_iso() in completed_dates,
    }


def challenges_payload(user_id: str, user: dict) -> dict:
    challenges = []
    for doc in db.collection("challenges").stream():
        challenge = doc.to_dict() or {}
        if challenge.get("status", "active") == "hidden":
            continue
        challenges.append(challenge_payload(doc.id, challenge, user_id, user))
    challenges.sort(
        key=lambda item: (
            0 if item["available"] else 1,
            0 if item["participant_status"] == "active" else 1,
            item["required_subscription"],
            item["title"],
        )
    )
    return {"challenges": challenges}


@app.post("/auth", response_model=ProfileResponse)
async def auth(request: AuthRequest):
    _, user = current_user_from_init(request.initData)
    return profile_payload(user)


@app.post("/habit")
async def mark_habit(request: HabitRequest):
    telegram_id, user = current_user_from_init(request.initData)
    habit = request.habit
    allowed_codes = {item["code"] for item in get_habit_items(user)}
    if habit not in allowed_codes:
        raise HTTPException(status_code=400, detail="Habit is not available for your subscription")

    today = today_iso()
    user_ref = db.collection("users").document(telegram_id)
    habits = user.get("habits", {}) or {}
    last_date = user.get("last_action_date")

    if last_date != today:
        habits = empty_habits_for(user)
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
        user["habits"] = habits
        user["last_action_date"] = today
        return {
            "ok": False,
            "message": "Эта привычка уже отмечена сегодня.",
            "xp": user.get("xp", 0),
            "streak": streak,
            "level": compute_level(user.get("xp", 0)),
            "habits": today_habits(user),
            "habit_items": get_habit_items(user),
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
    user.update({"xp": new_xp, "streak": streak, "last_action_date": today, "habits": habits})

    return {
        "ok": True,
        "new_xp": new_xp,
        "new_streak": streak,
        "level": compute_level(new_xp),
        "habits": today_habits(user),
        "habit_items": get_habit_items(user),
        "message": f"+10 XP! Серия: {streak} дн.",
    }


@app.post("/habit/edit")
async def edit_habit(request: HabitEditRequest):
    telegram_id, user = current_user_from_init(request.initData)
    title = request.title.strip()[:32]
    if len(title) < 2:
        raise HTTPException(status_code=400, detail="Habit title is too short")

    code = request.code
    icon = normalize_icon(request.icon, "")
    caption = normalize_caption(request.caption)
    default_codes = {habit["code"] for habit in DEFAULT_HABITS}
    user_ref = db.collection("users").document(telegram_id)

    if code in default_codes:
        updates = {f"habit_settings.{code}.title": title}
        if icon:
            updates[f"habit_settings.{code}.icon"] = icon
        updates[f"habit_settings.{code}.caption"] = caption
        user_ref.update(updates)
        user.setdefault("habit_settings", {}).setdefault(code, {})["title"] = title
        if icon:
            user["habit_settings"][code]["icon"] = icon
        user["habit_settings"][code]["caption"] = caption
        return {"ok": True, "profile": profile_payload(user)}

    custom_habits = user.get("custom_habits") or []
    for habit in custom_habits:
        if habit.get("code") == code:
            habit["title"] = title
            if icon:
                habit["icon"] = icon
            habit["caption"] = caption
            user_ref.update({"custom_habits": custom_habits})
            user["custom_habits"] = custom_habits
            return {"ok": True, "profile": profile_payload(user)}

    raise HTTPException(status_code=404, detail="Habit not found")


@app.post("/habit/add")
async def add_habit(request: HabitAddRequest):
    telegram_id, user = current_user_from_init(request.initData)
    title = request.title.strip()[:32]
    if len(title) < 2:
        raise HTTPException(status_code=400, detail="Habit title is too short")

    subscription = normalize_subscription(user.get("subscription"))
    limit = CUSTOM_HABIT_LIMITS[subscription]
    custom_habits = user.get("custom_habits") or []
    if len(custom_habits) >= limit:
        raise HTTPException(status_code=403, detail="Habit limit reached for your subscription")

    new_habit = {
        "code": f"custom_{int(time.time())}_{len(custom_habits) + 1}",
        "title": title,
        "icon": normalize_icon(request.icon),
        "caption": normalize_caption(request.caption),
    }
    custom_habits.append(new_habit)
    db.collection("users").document(telegram_id).update({"custom_habits": custom_habits})
    user["custom_habits"] = custom_habits
    return {"ok": True, "profile": profile_payload(user)}


@app.post("/habit/delete")
async def delete_habit(request: HabitDeleteRequest):
    telegram_id, user = current_user_from_init(request.initData)
    if request.code in {habit["code"] for habit in DEFAULT_HABITS}:
        raise HTTPException(status_code=400, detail="Default habits can only be renamed")

    custom_habits = [
        habit for habit in (user.get("custom_habits") or []) if habit.get("code") != request.code
    ]
    if len(custom_habits) == len(user.get("custom_habits") or []):
        raise HTTPException(status_code=404, detail="Habit not found")

    db.collection("users").document(telegram_id).update({"custom_habits": custom_habits})
    user["custom_habits"] = custom_habits
    return {"ok": True, "profile": profile_payload(user)}


@app.post("/progress")
async def get_progress(request: AuthRequest):
    _, user = current_user_from_init(request.initData)
    return progress_payload(user)


@app.post("/progress/add")
async def add_progress(request: ProgressAddRequest):
    telegram_id, user = current_user_from_init(request.initData)
    created_at = now_iso()
    entry = {
        "id": f"progress_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}",
        "date": today_iso(),
        "created_at": created_at,
        "weight": clean_measure(request.weight),
        "waist": clean_measure(request.waist),
        "chest": clean_measure(request.chest),
        "arm": clean_measure(request.arm),
        "thigh": clean_measure(request.thigh),
        "note": (request.note or "").strip()[:160],
    }
    if all(entry[key] is None for key in ("weight", "waist", "chest", "arm", "thigh")) and not entry["note"]:
        raise HTTPException(status_code=400, detail="Add at least one measurement")

    entries = user.get("progress_entries") or []
    entries.append(entry)
    entries = sorted(
        entries,
        key=lambda item: item.get("created_at") or item.get("date", "") or "",
        reverse=True,
    )[:50]
    db.collection("users").document(telegram_id).update({"progress_entries": entries})
    user["progress_entries"] = entries
    return {"ok": True, **progress_payload(user)}


@app.post("/progress/delete")
async def delete_progress(request: ProgressDeleteRequest):
    telegram_id, user = current_user_from_init(request.initData)
    entries = user.get("progress_entries") or []
    filtered_entries = [entry for entry in entries if entry.get("id") != request.entry_id]
    if len(filtered_entries) == len(entries):
        raise HTTPException(status_code=404, detail="Progress entry not found")

    db.collection("users").document(telegram_id).update({"progress_entries": filtered_entries})
    user["progress_entries"] = filtered_entries
    return {"ok": True, **progress_payload(user)}


@app.post("/challenges")
async def get_challenges(request: AuthRequest):
    telegram_id, user = current_user_from_init(request.initData)
    return challenges_payload(telegram_id, user)


@app.post("/challenge/join")
async def join_challenge(request: ChallengeActionRequest):
    telegram_id, user = current_user_from_init(request.initData)
    challenge_ref = db.collection("challenges").document(request.challenge_id)
    challenge_doc = challenge_ref.get()
    if not challenge_doc.exists:
        raise HTTPException(status_code=404, detail="Challenge not found")

    challenge = challenge_doc.to_dict() or {}
    if challenge.get("status", "active") != "active":
        raise HTTPException(status_code=400, detail="Challenge is not active")
    if not can_access(effective_subscription(user), challenge.get("required_subscription", "free")):
        raise HTTPException(status_code=403, detail="Subscription required")

    participant_ref = db.collection("challenge_participants").document(
        participant_doc_id(telegram_id, request.challenge_id)
    )
    if not participant_ref.get().exists:
        participant_ref.set(
            {
                "challenge_id": request.challenge_id,
                "user_id": telegram_id,
                "joined_at": now_iso(),
                "completed_dates": [],
                "status": "active",
                "reward_claimed": False,
            }
        )
        challenge_ref.update({"participants_count": firestore.Increment(1)})

    user = db.collection("users").document(telegram_id).get().to_dict() or user
    return {"ok": True, **challenges_payload(telegram_id, user)}


@app.post("/challenge/check")
async def check_challenge(request: ChallengeActionRequest):
    telegram_id, user = current_user_from_init(request.initData)
    challenge_ref = db.collection("challenges").document(request.challenge_id)
    challenge_doc = challenge_ref.get()
    if not challenge_doc.exists:
        raise HTTPException(status_code=404, detail="Challenge not found")

    challenge = challenge_doc.to_dict() or {}
    participant_ref = db.collection("challenge_participants").document(
        participant_doc_id(telegram_id, request.challenge_id)
    )
    participant_doc = participant_ref.get()
    if not participant_doc.exists:
        raise HTTPException(status_code=400, detail="Join challenge first")

    participant = participant_doc.to_dict() or {}
    if participant.get("status") == "completed":
        return {"ok": True, "message": "Challenge already completed", **challenges_payload(telegram_id, user)}

    today = today_iso()
    completed_dates = participant.get("completed_dates") or []
    if today in completed_dates:
        raise HTTPException(status_code=400, detail="Already checked today")

    completed_dates.append(today)
    duration_days = int(challenge.get("duration_days") or 7)
    update_data = {"completed_dates": completed_dates, "last_check_date": today}
    completed_now = len(completed_dates) >= duration_days
    if completed_now:
        update_data["status"] = "completed"
        update_data["completed_at"] = now_iso()
        if not participant.get("reward_claimed"):
            reward_xp = int(challenge.get("reward_xp") or 0)
            update_data["reward_claimed"] = True
            db.collection("users").document(telegram_id).update({"xp": firestore.Increment(reward_xp)})

    participant_ref.update(update_data)
    user = db.collection("users").document(telegram_id).get().to_dict() or user
    return {"ok": True, **challenges_payload(telegram_id, user)}


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


@app.get("/leaderboard")
async def get_leaderboard():
    users = []
    for doc in db.collection("users").stream():
        data = doc.to_dict()
        xp = data.get("xp", 0)
        users.append(
            {
                "id": doc.id,
                "name": data.get("name", "Без имени"),
                "username": data.get("username"),
                "xp": xp,
                "streak": data.get("streak", 0),
                "level": compute_level(xp),
            }
        )

    users.sort(key=lambda item: item["xp"], reverse=True)
    top = [{**user, "place": index + 1} for index, user in enumerate(users[:10])]
    levels = [
        {"xp": xp, "title": title}
        for xp, title in sorted(LEVELS.items(), key=lambda item: item[0])
    ]
    return {"top": top, "levels": levels}


@app.get("/health")
async def health():
    return {"status": "ok"}
