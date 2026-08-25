
from pydantic import BaseModel


class LocationPayload(BaseModel):
    latitude: float
    longitude: float
    elevation: float
    name: str | None = None
