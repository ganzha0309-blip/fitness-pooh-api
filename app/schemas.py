from typing import Optional

from pydantic import BaseModel


class AuthRequest(BaseModel):
    initData: str


class HabitRequest(BaseModel):
    initData: str
    habit: str


class HabitEditRequest(BaseModel):
    initData: str
    code: str
    title: str
    icon: Optional[str] = None
    caption: Optional[str] = None


class HabitAddRequest(BaseModel):
    initData: str
    title: str
    icon: Optional[str] = None
    caption: Optional[str] = None


class HabitDeleteRequest(BaseModel):
    initData: str
    code: str


class ProgressAddRequest(BaseModel):
    initData: str
    weight: Optional[float] = None
    waist: Optional[float] = None
    chest: Optional[float] = None
    arm: Optional[float] = None
    thigh: Optional[float] = None
    note: Optional[str] = None


class ProgressDeleteRequest(BaseModel):
    initData: str
    entry_id: str


class ChallengeActionRequest(BaseModel):
    initData: str
    challenge_id: str


class ProfileResponse(BaseModel):
    name: str
    xp: int
    streak: int
    subscription: str
    subscription_until: Optional[str] = None
    username: Optional[str] = None
    last_action_date: Optional[str] = None
    level: str
    habits: dict[str, int]
    habit_items: list[dict]
    custom_habit_limit: int
    custom_habit_count: int
