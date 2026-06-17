from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class ExternalPlaceSource(StrEnum):
    KAKAO = "KAKAO"
    NAVER = "NAVER"
    TOUR_API = "TOUR_API"
    PUBLIC_DATA = "PUBLIC_DATA"


class PlaceCategory(StrEnum):
    TOURIST_ATTRACTION = "TOURIST_ATTRACTION"
    RESTAURANT = "RESTAURANT"
    CAFE = "CAFE"
    LODGING = "LODGING"
    MARKET = "MARKET"
    CULTURE = "CULTURE"
    ACTIVITY = "ACTIVITY"
    ETC = "ETC"


class NormalizedPlace(BaseModel):
    source: ExternalPlaceSource
    source_place_id: str
    name: str = Field(min_length=1)
    region_name: str = Field(min_length=1)
    address: str = ""
    road_address: str = ""
    latitude: float
    longitude: float
    category: PlaceCategory
    source_query: str = Field(min_length=1)
    raw_category: str = ""
    phone: str = ""
    url: str = ""
    image_url: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    sources: list[ExternalPlaceSource] = Field(default_factory=list)
    source_place_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def fill_source_lists(self) -> "NormalizedPlace":
        if not self.sources:
            self.sources = [self.source]
        if not self.source_place_ids:
            self.source_place_ids = [self.source_place_id]
        return self


class PlaceCollectionResult(BaseModel):
    region_name: str
    queries: list[str]
    processed_places: list[NormalizedPlace]
