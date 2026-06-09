import os
from datetime import timedelta, timezone

from dotenv import load_dotenv


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set")

MSK = timezone(timedelta(hours=3))

DEFAULT_HABITS = [
    {"code": "water", "title": "Вода", "icon": "💧", "caption": "2 литра за день", "is_default": True},
    {
        "code": "workout",
        "title": "Тренировка",
        "icon": "🏋️",
        "caption": "Любая активность",
        "is_default": True,
    },
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
