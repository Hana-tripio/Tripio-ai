import re
import time
from collections.abc import Callable
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
        retry_attempts: int = 2,
        retry_backoff_seconds: tuple[float, ...] = (1.0, 2.0),
        min_interval_seconds: float = 0.7,
        sleep_func: Callable[[float], None] | None = None,
        clock_func: Callable[[], float] | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client or httpx.Client(timeout=10.0)
        self.retry_attempts = max(retry_attempts, 0)
        self.retry_backoff_seconds = retry_backoff_seconds or (0.0,)
        self.min_interval_seconds = max(min_interval_seconds, 0.0)
        self.sleep_func = sleep_func or time.sleep
        self.clock_func = clock_func or time.monotonic
        self._last_request_at: float | None = None

    def search_local(
        self,
        query: str,
        *,
        display: int = 5,
        start: int = 1,
        sort: str = "random",
    ) -> list[NaverLocalPlace]:
        self._wait_for_min_interval()
        for attempt in range(self.retry_attempts + 1):
            response = self.http_client.get(
                f"{self.base_url}/v1/search/local.json",
                params={"query": query, "display": display, "start": start, "sort": sort},
                headers={
                    "X-Naver-Client-Id": self.client_id,
                    "X-Naver-Client-Secret": self.client_secret,
                },
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                if response.status_code == 429 and attempt < self.retry_attempts:
                    delay = self.retry_backoff_seconds[min(attempt, len(self.retry_backoff_seconds) - 1)]
                    self.sleep_func(delay)
                    continue
                raise

            payload: dict[str, Any] = response.json()
            return [NaverLocalPlace.model_validate(item) for item in payload.get("items", [])]

        return []

    def _wait_for_min_interval(self) -> None:
        if self._last_request_at is None or self.min_interval_seconds <= 0:
            self._last_request_at = self.clock_func()
            return

        now = self.clock_func()
        elapsed = now - self._last_request_at
        if elapsed < self.min_interval_seconds:
            self.sleep_func(self.min_interval_seconds - elapsed)
        self._last_request_at = self.clock_func()
