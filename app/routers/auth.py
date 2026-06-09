from fastapi import APIRouter

from app.schemas import AuthRequest, ProfileResponse
from app.services.users import current_user_from_init, profile_payload


router = APIRouter()


@router.post("/auth", response_model=ProfileResponse)
async def auth(request: AuthRequest):
    _, user = current_user_from_init(request.initData)
    return profile_payload(user)
