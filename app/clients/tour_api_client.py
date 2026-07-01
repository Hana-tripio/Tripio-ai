from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field


class TourApiPlace(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    content_id: str = Field(alias="contentid")
    content_type_id: str = Field(default="", alias="contenttypeid")
    title: str
    address: str = Field(default="", alias="addr1")
    address_detail: str = Field(default="", alias="addr2")
    map_x: str = Field(default="0", alias="mapx")
    map_y: str = Field(default="0", alias="mapy")
    image_url: str = Field(default="", alias="firstimage")
    thumbnail_url: str = Field(default="", alias="firstimage2")
    tel: str = ""
    cat1: str = ""
    cat2: str = ""
    cat3: str = ""
    event_start_date: str = Field(default="", alias="eventstartdate")
    event_end_date: str = Field(default="", alias="eventenddate")

    @property
    def longitude(self) -> float:
        return float(self.map_x or 0)

    @property
    def latitude(self) -> float:
        return float(self.map_y or 0)


class TourApiClient:
    def __init__(
        self,
        service_key: str,
        *,
        http_client: httpx.Client | None = None,
        base_url: str = "https://apis.data.go.kr/B551011/KorService2",
        mobile_os: str = "ETC",
        mobile_app: str = "Tripio",
    ) -> None:
        self.service_key = service_key
        self.base_url = base_url.rstrip("/")
        self.mobile_os = mobile_os
        self.mobile_app = mobile_app
        self.http_client = http_client or httpx.Client(timeout=10.0)

    def search_keyword(
        self,
        keyword: str,
        *,
        rows: int = 20,
        page: int = 1,
    ) -> list[TourApiPlace]:
        return self._get_places(
            "searchKeyword2",
            {"keyword": keyword, "numOfRows": rows, "pageNo": page},
        )

    def search_festivals(
        self,
        *,
        event_start_date: str,
        event_end_date: str | None = None,
        area_code: int | None = None,
        sigungu_code: int | None = None,
        rows: int = 20,
        page: int = 1,
    ) -> list[TourApiPlace]:
        params: dict[str, str | int] = {
            "eventStartDate": event_start_date,
            "numOfRows": rows,
            "pageNo": page,
        }
        if event_end_date:
            params["eventEndDate"] = event_end_date
        if area_code is not None:
            params["areaCode"] = area_code
        if sigungu_code is not None:
            params["sigunguCode"] = sigungu_code
        return self._get_places("searchFestival2", params)

    def search_stays(self, *, rows: int = 20, page: int = 1) -> list[TourApiPlace]:
        return self._get_places("searchStay2", {"numOfRows": rows, "pageNo": page})

    def _get_places(self, endpoint: str, params: dict[str, str | int]) -> list[TourApiPlace]:
        response = self.http_client.get(
            f"{self.base_url}/{endpoint}",
            params={
                "serviceKey": self.service_key,
                "MobileOS": self.mobile_os,
                "MobileApp": self.mobile_app,
                "_type": "json",
                **params,
            },
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        header = payload.get("response", {}).get("header", {})
        if header.get("resultCode") != "0000":
            message = header.get("resultMsg", "TourAPI request failed")
            raise ValueError(f"TourAPI request failed: {message}")
        body = payload.get("response", {}).get("body", {})
        raw_items = body.get("items", {})
        if isinstance(raw_items, str):
            return []
        items = raw_items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        return [TourApiPlace.model_validate(item) for item in items]
