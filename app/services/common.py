import hashlib
import hmac
import json
from datetime import date, datetime
from urllib.parse import parse_qs, unquote

from fastapi import HTTPException

from app.config import BOT_TOKEN, CUSTOM_HABIT_LIMITS, LEVELS, MSK, SUBSCRIPTION_ORDER


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
