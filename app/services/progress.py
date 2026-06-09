from typing import Optional

from fastapi import HTTPException


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
