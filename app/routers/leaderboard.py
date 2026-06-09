from fastapi import APIRouter

from app.services.leaderboard import leaderboard_payload


router = APIRouter()


@router.get("/leaderboard")
async def get_leaderboard():
    return leaderboard_payload()
