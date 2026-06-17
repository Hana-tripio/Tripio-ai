import re
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, field_validator

TAG_PATTERN = re.compile(r"<[^>]+>")


class NaverLocalPlace(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    link: str = ""
    category: str = ""
    description: str = ""
    address: str = ""
    roadAddress: str = ""
    mapx: str
    mapy: str

    @field_validator("title")
    @classmethod
    def strip_html_tags(cls, value: str) -> str:
        return TAG_PATTERN.sub("", value)

    @property
    def longitude(self) -> float:
        return int(self.mapx) / 10_000_000

    @property
    def latitude(self) -> float:
        return int(self.mapy) / 10_000_000


class NaverLocalClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        http_client: httpx.Client | None = None,
        base_url: str = "https://openapi.naver.com",
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client or httpx.Client(timeout=10.0)

    def search_local(
        self,
        query: str,
        *,
        display: int = 5,
        sort: str = "random",
    ) -> list[NaverLocalPlace]:
        response = self.http_client.get(
            f"{self.base_url}/v1/search/local.json",
            params={"query": query, "display": display, "sort": sort},
            headers={
                "X-Naver-Client-Id": self.client_id,
                "X-Naver-Client-Secret": self.client_secret,
            },
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return [NaverLocalPlace.model_validate(item) for item in payload.get("items", [])]

