from app.firebase import db
from app.services.common import (
    can_access,
    effective_subscription,
    normalize_subscription,
    participant_doc_id,
    today_iso,
)


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
