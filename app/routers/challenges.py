from fastapi import APIRouter, HTTPException
from firebase_admin import firestore

from app.firebase import db
from app.schemas import AuthRequest, ChallengeActionRequest
from app.services.challenges import challenges_payload
from app.services.common import (
    can_access,
    effective_subscription,
    now_iso,
    participant_doc_id,
    today_iso,
)
from app.services.users import current_user_from_init


router = APIRouter()


@router.post("/challenges")
async def get_challenges(request: AuthRequest):
    telegram_id, user = current_user_from_init(request.initData)
    return challenges_payload(telegram_id, user)


@router.post("/challenge/join")
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


@router.post("/challenge/check")
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
