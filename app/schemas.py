from pydantic import BaseModel
from typing import Optional


class PlayerCreate(BaseModel):
    name: str
    nickname: Optional[str] = None
    license_number: str | None = None
    photo_url: str | None = None
    hcp_exact: float = 0.0
    active: bool = True


class PlayerUpdate(PlayerCreate):
    pass


class CourseCreate(BaseModel):
    name: str
    city: Optional[str] = None
    par_total: int = 72
    slope_yellow: int = 113
    rating_yellow: float = 72.0
    meters_total: Optional[int] = None
    logo_url: Optional[str] = None

class CourseUpdate(CourseCreate):
    pass

class HoleCreate(BaseModel):
    number: int
    par: int
    stroke_index: int
    meters_yellow: Optional[int] = None
