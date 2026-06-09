import time
from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.config import CUSTOM_HABIT_LIMITS, DEFAULT_HABITS, MSK
from app.firebase import db
from app.schemas import HabitAddRequest, HabitDeleteRequest, HabitEditRequest, HabitRequest
from app.services.common import (
    compute_level,
    normalize_caption,
    normalize_icon,
    normalize_subscription,
    today_iso,
)
from app.services.users import (
    current_user_from_init,
    empty_habits_for,
    get_habit_items,
    profile_payload,
    today_habits,
)


router = APIRouter()


@router.post("/habit")
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


@router.post("/habit/edit")
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


@router.post("/habit/add")
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


@router.post("/habit/delete")
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
