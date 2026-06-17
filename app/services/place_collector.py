import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from app.schemas.place_source import NormalizedPlace, PlaceCollectionResult
from app.services.place_deduplicator import deduplicate_places
from app.services.place_normalizer import (
    normalize_kakao_place,
    normalize_naver_place,
    normalize_tour_place,
)


class KakaoSearchClient(Protocol):
    def search_keyword(self, query: str, *, size: int = 15) -> list[object]:
        pass


class NaverSearchClient(Protocol):
    def search_local(self, query: str, *, display: int = 5, sort: str = "random") -> list[object]:
        pass


class TourSearchClient(Protocol):
    def search_keyword(self, keyword: str, *, rows: int = 20) -> list[object]:
        pass


@dataclass(frozen=True)
class PlaceCollector:
    kakao_client: KakaoSearchClient
    naver_client: NaverSearchClient
    output_root: Path
    tour_client: TourSearchClient | None = None

    def collect(
        self,
        *,
        region_name: str,
        queries: list[str],
        tour_keywords: list[str] | None = None,
        kakao_size: int = 15,
        naver_display: int = 5,
        tour_rows: int = 20,
    ) -> PlaceCollectionResult:
        normalized_places: list[NormalizedPlace] = []

        for query in queries:
            kakao_results = self.kakao_client.search_keyword(query, size=kakao_size)
            naver_results = self.naver_client.search_local(query, display=naver_display)

            self._write_json(
                self.output_root / "raw" / "kakao" / f"{_slug(region_name)}_{_slug(query)}.json",
                [_dump_item(item) for item in kakao_results],
            )
            self._write_json(
                self.output_root / "raw" / "naver" / f"{_slug(region_name)}_{_slug(query)}.json",
                [_dump_item(item) for item in naver_results],
            )

            normalized_places.extend(
                normalize_kakao_place(item, region_name=region_name, query=query)
                for item in kakao_results
            )
            normalized_places.extend(
                normalize_naver_place(item, region_name=region_name, query=query)
                for item in naver_results
            )

        if self.tour_client and tour_keywords:
            for keyword in tour_keywords:
                tour_results = self.tour_client.search_keyword(keyword, rows=tour_rows)
                self._write_json(
                    self.output_root
                    / "raw"
                    / "tour_api"
                    / f"{_slug(region_name)}_{_slug(keyword)}.json",
                    [_dump_item(item) for item in tour_results],
                )
                normalized_places.extend(
                    normalize_tour_place(item, region_name=region_name, query=keyword)
                    for item in tour_results
                )

        processed_places = deduplicate_places(normalized_places)
        self._write_json(
            self.output_root / "processed" / f"{_slug(region_name)}_places.json",
            [place.model_dump(mode="json") for place in processed_places],
        )

        return PlaceCollectionResult(
            region_name=region_name,
            queries=queries,
            processed_places=processed_places,
        )

    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _dump_item(item: object) -> object:
    if isinstance(item, BaseModel):
        return item.model_dump(mode="json")
    return item


def _slug(value: str) -> str:
    normalized = value.strip().lower()
    replacements = {
        "공주": "gongju",
        "대전": "daejeon",
        "청주": "cheongju",
        "관광지": "tourist-attraction",
        "명소": "attraction",
        "카페": "cafe",
        "맛집": "restaurant",
        "시장": "market",
        "숙소": "lodging",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    normalized = re.sub(r"[^a-z0-9가-힣]+", "-", normalized)
    normalized = normalized.strip("-")
    return normalized or "query"
