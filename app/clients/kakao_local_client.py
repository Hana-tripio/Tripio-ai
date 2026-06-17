from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict


class KakaoKeywordPlace(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    place_name: str
    category_name: str = ""
    category_group_code: str = ""
    road_address_name: str = ""
    address_name: str = ""
    x: str
    y: str
    phone: str = ""
    place_url: str = ""

    @property
    def longitude(self) -> float:
        return float(self.x)

    @property
    def latitude(self) -> float:
        return float(self.y)


class KakaoLocalClient:
    def __init__(
        self,
        api_key: str,
        *,
        http_client: httpx.Client | None = None,
        base_url: str = "https://dapi.kakao.com",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client or httpx.Client(timeout=10.0)

    def search_keyword(self, query: str, *, size: int = 15) -> list[KakaoKeywordPlace]:
        response = self.http_client.get(
            f"{self.base_url}/v2/local/search/keyword.json",
            params={"query": query, "size": size},
            headers={"Authorization": f"KakaoAK {self.api_key}"},
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return [KakaoKeywordPlace.model_validate(item) for item in payload.get("documents", [])]

