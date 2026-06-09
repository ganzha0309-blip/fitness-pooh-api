import time
import uuid

from fastapi import APIRouter, HTTPException

from app.firebase import db
from app.schemas import AuthRequest, ProgressAddRequest, ProgressDeleteRequest
from app.services.common import now_iso, today_iso
from app.services.progress import clean_measure, progress_payload
from app.services.users import current_user_from_init


router = APIRouter()


@router.post("/progress")
async def get_progress(request: AuthRequest):
    _, user = current_user_from_init(request.initData)
    return progress_payload(user)


@router.post("/progress/add")
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


@router.post("/progress/delete")
async def delete_progress(request: ProgressDeleteRequest):
    telegram_id, user = current_user_from_init(request.initData)
    entries = user.get("progress_entries") or []
    filtered_entries = [entry for entry in entries if entry.get("id") != request.entry_id]
    if len(filtered_entries) == len(entries):
        raise HTTPException(status_code=404, detail="Progress entry not found")

    db.collection("users").document(telegram_id).update({"progress_entries": filtered_entries})
    user["progress_entries"] = filtered_entries
    return {"ok": True, **progress_payload(user)}
