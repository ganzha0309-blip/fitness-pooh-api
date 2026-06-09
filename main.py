from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, challenges, habits, health, leaderboard, progress, trainings


app = FastAPI(title="Fitness Pooh API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(habits.router)
app.include_router(progress.router)
app.include_router(challenges.router)
app.include_router(trainings.router)
app.include_router(leaderboard.router)
app.include_router(health.router)
