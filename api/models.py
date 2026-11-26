"""Request models shared by the routes; they bound every value a client may store."""
from pydantic import BaseModel, ConfigDict, Field, field_validator


class LocationPayload(BaseModel):
    """An observer location as the clients send it."""
    model_config = ConfigDict(extra='ignore')

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    elevation: float = Field(default=0.0, ge=-500, le=9000)
    name: str | None = Field(default=None, max_length=120)
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator('elevation', mode='before')
    @classmethod
    def _missing_elevation_is_sea_level(cls, value):
        # The page sends null when an elevation lookup failed.
        return 0.0 if value is None else value


class MagnitudeFilters(BaseModel):
    """Per-user display limits; the dialog offers 10 to 20."""
    model_config = ConfigDict(extra='ignore')

    asteroidMaxMagnitude: float | None = Field(default=None, ge=0, le=25)
    cometMaxMagnitude: float | None = Field(default=None, ge=0, le=25)
