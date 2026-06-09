from app.config import CUSTOM_HABIT_LIMITS, DEFAULT_HABITS
from app.firebase import db
from app.schemas import ProfileResponse
from app.services.common import (
    compute_level,
    effective_subscription,
    normalize_icon,
    today_iso,
    verify_init_data,
)


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
