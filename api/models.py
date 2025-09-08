from typing import Optional
from pydantic import BaseModel

class LocationPayload(BaseModel):
    latitude: float
    longitude: float
    elevation: float
    name: Optional[str] = None

class PrecomputeRangeRequest(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None
    elevation: Optional[float] = None
    start_date: str
    end_date: str
