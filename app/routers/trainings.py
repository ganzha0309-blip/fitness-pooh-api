from fastapi import APIRouter

from app.services.trainings import trainings_payload


router = APIRouter()


@router.get("/trainings")
async def get_trainings():
    return trainings_payload()
