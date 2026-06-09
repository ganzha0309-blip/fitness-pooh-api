from app.config import LEVELS
from app.firebase import db
from app.services.common import compute_level


def leaderboard_payload() -> dict:
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
