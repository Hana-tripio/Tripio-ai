import json
import re
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol, TypeVar

import httpx
from pydantic import BaseModel

from app.schemas.place_source import (
    NormalizedPlace,
    PlaceCollectionResult,
)
from app.services.place_deduplicator import deduplicate_places
from app.services.place_normalizer import (
    normalize_kakao_place,
    normalize_naver_place,
    normalize_tour_place,
)
from app.services.place_quality import refine_place_quality

T = TypeVar("T")


class KakaoSearchClient(Protocol):
    def search_keyword(self, query: str, *, size: int = 15, page: int = 1) -> list[object]:
        pass


class NaverSearchClient(Protocol):
    def search_local(
        self,
        query: str,
        *,
        display: int = 5,
        start: int = 1,
        sort: str = "random",
    ) -> list[object]:
        pass


class TourSearchClient(Protocol):
    def search_keyword(self, keyword: str, *, rows: int = 20, page: int = 1) -> list[object]:
        pass

    def search_festivals(
        self,
        *,
        event_start_date: str,
        event_end_date: str | None = None,
        area_code: int | None = None,
        sigungu_code: int | None = None,
        rows: int = 20,
        page: int = 1,
    ) -> list[object]:
        pass

    def search_stays(self, *, rows: int = 20, page: int = 1) -> list[object]:
        pass


@dataclass(frozen=True)
class PlaceCollector:
    kakao_client: KakaoSearchClient | None
    naver_client: NaverSearchClient | None
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
        kakao_pages: int = 1,
        naver_pages: int = 1,
        tour_pages: int = 1,
        include_tour_festivals: bool = False,
        include_tour_stays: bool = False,
        festival_start_date: str | None = None,
        festival_end_date: str | None = None,
        kakao_concurrency: int = 1,
        naver_concurrency: int = 1,
        tour_concurrency: int = 1,
    ) -> PlaceCollectionResult:
        normalized_places: list[NormalizedPlace] = []
        warnings: list[str] = []
        source_jobs: list[Callable[[], tuple[list[NormalizedPlace], list[str]]]] = []

        if self.kakao_client:
            source_jobs.append(
                lambda: self._collect_kakao_source(
                    region_name=region_name,
                    queries=queries,
                    size=kakao_size,
                    pages=kakao_pages,
                    concurrency=kakao_concurrency,
                )
            )
        if self.naver_client:
            source_jobs.append(
                lambda: self._collect_naver_source(
                    region_name=region_name,
                    queries=queries,
                    display=naver_display,
                    pages=naver_pages,
                    concurrency=naver_concurrency,
                )
            )
        if self.tour_client and (tour_keywords or include_tour_festivals or include_tour_stays):
            source_jobs.append(
                lambda: self._collect_tour_source(
                    region_name=region_name,
                    tour_keywords=tour_keywords,
                    rows=tour_rows,
                    pages=tour_pages,
                    include_tour_festivals=include_tour_festivals,
                    include_tour_stays=include_tour_stays,
                    festival_start_date=festival_start_date,
                    festival_end_date=festival_end_date,
                    concurrency=tour_concurrency,
                )
            )

        for places_chunk, warnings_chunk in self._run_parallel_jobs(source_jobs):
            normalized_places.extend(places_chunk)
            warnings.extend(warnings_chunk)

        # Collector-side exclusions and region filtering happen before dedupe and
        # quality refinement, so the quality summary starts from the candidates
        # that survive this gate.
        normalized_places = _filter_places_by_region(normalized_places, region_name=region_name)
        deduplicated_places = deduplicate_places(normalized_places)
        quality_result = refine_place_quality(deduplicated_places)
        processed_places = quality_result.kept_places
        self._write_json(
            self.output_root / "processed" / f"{_slug(region_name)}_places.json",
            [place.model_dump(mode="json") for place in processed_places],
        )
        self._write_json(
            self.output_root
            / "processed"
            / "reports"
            / f"{_slug(region_name)}_quality_report.json",
            quality_result.report.model_dump(mode="json"),
        )

        return PlaceCollectionResult(
            region_name=region_name,
            queries=queries,
            processed_places=processed_places,
            quality_summary=quality_result.summary,
            warnings=warnings,
        )

    def _collect_kakao_source(
        self,
        *,
        region_name: str,
        queries: list[str],
        size: int,
        pages: int,
        concurrency: int,
    ) -> tuple[list[NormalizedPlace], list[str]]:
        tasks = self._map_with_concurrency(
            queries,
            concurrency,
            lambda query: self._collect_kakao_query(region_name, query, size, pages),
        )
        normalized_places: list[NormalizedPlace] = []
        warnings: list[str] = []
        for places_chunk, warnings_chunk in tasks:
            normalized_places.extend(places_chunk)
            warnings.extend(warnings_chunk)
        return normalized_places, warnings

    def _collect_naver_source(
        self,
        *,
        region_name: str,
        queries: list[str],
        display: int,
        pages: int,
        concurrency: int,
    ) -> tuple[list[NormalizedPlace], list[str]]:
        tasks = self._map_with_concurrency(
            queries,
            concurrency,
            lambda query: self._collect_naver_query(region_name, query, display, pages),
        )
        normalized_places: list[NormalizedPlace] = []
        warnings: list[str] = []
        for places_chunk, warnings_chunk in tasks:
            normalized_places.extend(places_chunk)
            warnings.extend(warnings_chunk)
        return normalized_places, warnings

    def _collect_tour_source(
        self,
        *,
        region_name: str,
        tour_keywords: list[str] | None,
        rows: int,
        pages: int,
        include_tour_festivals: bool,
        include_tour_stays: bool,
        festival_start_date: str | None,
        festival_end_date: str | None,
        concurrency: int,
    ) -> tuple[list[NormalizedPlace], list[str]]:
        task_specs: list[tuple[str, str | None]] = [
            ("keyword", keyword) for keyword in (tour_keywords or [])
        ]
        if include_tour_festivals:
            task_specs.append(("festival", None))
        if include_tour_stays:
            task_specs.append(("stay", None))

        tasks = self._map_with_concurrency(
            task_specs,
            concurrency,
            lambda task: self._collect_tour_task(
                region_name=region_name,
                task_type=task[0],
                task_value=task[1],
                rows=rows,
                pages=pages,
                festival_start_date=festival_start_date,
                festival_end_date=festival_end_date,
            ),
        )
        normalized_places: list[NormalizedPlace] = []
        warnings: list[str] = []
        for places_chunk, warnings_chunk in tasks:
            normalized_places.extend(places_chunk)
            warnings.extend(warnings_chunk)
        return normalized_places, warnings

    def _collect_kakao_query(
        self,
        region_name: str,
        query: str,
        size: int,
        pages: int,
    ) -> tuple[list[NormalizedPlace], list[str]]:
        warnings: list[str] = []
        kakao_results = self._collect_kakao_pages(query, size, pages, warnings)
        self._write_json(
            self.output_root / "raw" / "kakao" / f"{_slug(region_name)}_{_slug(query)}.json",
            [_dump_item(item) for item in kakao_results],
        )
        return (
            [
                normalize_kakao_place(item, region_name=region_name, query=query)
                for item in kakao_results
            ],
            warnings,
        )

    def _collect_naver_query(
        self,
        region_name: str,
        query: str,
        display: int,
        pages: int,
    ) -> tuple[list[NormalizedPlace], list[str]]:
        warnings: list[str] = []
        naver_results = self._collect_naver_pages(query, display, pages, warnings)
        self._write_json(
            self.output_root / "raw" / "naver" / f"{_slug(region_name)}_{_slug(query)}.json",
            [_dump_item(item) for item in naver_results],
        )
        return (
            [
                normalize_naver_place(item, region_name=region_name, query=query)
                for item in naver_results
            ],
            warnings,
        )

    def _collect_tour_task(
        self,
        *,
        region_name: str,
        task_type: str,
        task_value: str | None,
        rows: int,
        pages: int,
        festival_start_date: str | None,
        festival_end_date: str | None,
    ) -> tuple[list[NormalizedPlace], list[str]]:
        warnings: list[str] = []
        if task_type == "keyword":
            if task_value is None:
                raise ValueError("TourAPI keyword task requires a keyword value")
            tour_results = self._collect_tour_keyword_pages(task_value, rows, pages, warnings)
            self._write_json(
                self.output_root
                / "raw"
                / "tour_api"
                / f"{_slug(region_name)}_{_slug(task_value)}.json",
                [_dump_item(item) for item in tour_results],
            )
            return (
                [
                    normalize_tour_place(item, region_name=region_name, query=task_value)
                    for item in tour_results
                ],
                warnings,
            )
        if task_type == "festival":
            start_date = festival_start_date or self._default_festival_start_date()
            end_date = festival_end_date or self._default_festival_end_date()
            festival_results = self._collect_tour_festival_pages(
                region_name=region_name,
                event_start_date=start_date,
                event_end_date=end_date,
                rows=rows,
                pages=pages,
                warnings=warnings,
            )
            self._write_json(
                self.output_root / "raw" / "tour_api" / f"{_slug(region_name)}_festivals.json",
                [_dump_item(item) for item in festival_results],
            )
            return (
                [
                    normalize_tour_place(item, region_name=region_name, query=f"{region_name} 축제")
                    for item in festival_results
                ],
                warnings,
            )
        if task_type == "stay":
            stay_results = self._collect_tour_stay_pages(rows=rows, pages=pages, warnings=warnings)
            self._write_json(
                self.output_root / "raw" / "tour_api" / f"{_slug(region_name)}_stays.json",
                [_dump_item(item) for item in stay_results],
            )
            return (
                [
                    normalize_tour_place(item, region_name=region_name, query=f"{region_name} 숙소")
                    for item in stay_results
                ],
                warnings,
            )
        raise ValueError(f"Unknown TourAPI task_type: {task_type}")

    def _run_parallel_jobs(
        self,
        jobs: list[Callable[[], T]],
    ) -> list[T]:
        if len(jobs) <= 1:
            return [job() for job in jobs]
        with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
            return list(executor.map(lambda job: job(), jobs))

    def _map_with_concurrency(
        self,
        values: Iterable[T],
        max_workers: int,
        worker: Callable[[T], tuple[list[NormalizedPlace], list[str]]],
    ) -> list[tuple[list[NormalizedPlace], list[str]]]:
        items = list(values)
        if len(items) <= 1 or max_workers <= 1:
            return [worker(item) for item in items]
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(executor.map(worker, items))

    def _collect_kakao_pages(
        self,
        query: str,
        size: int,
        pages: int,
        warnings: list[str],
    ) -> list[object]:
        collected: list[object] = []
        for page in range(1, max(pages, 1) + 1):
            try:
                if not self.kakao_client:
                    return collected
                results = self.kakao_client.search_keyword(query, size=size, page=page)
            except httpx.HTTPStatusError as exc:
                warnings.append(
                    "KAKAO_PAGE_FETCH_FAILED "
                    f"query={query} page={page} status={exc.response.status_code}"
                )
                break
            except httpx.HTTPError as exc:
                warnings.append(
                    "KAKAO_PAGE_FETCH_FAILED "
                    f"query={query} page={page} error={type(exc).__name__}"
                )
                break
            if not results:
                break
            collected.extend(results)
        return collected

    def _collect_naver_pages(
        self,
        query: str,
        display: int,
        pages: int,
        warnings: list[str],
    ) -> list[object]:
        collected: list[object] = []
        step = max(display, 1)
        for page_index in range(max(pages, 1)):
            start = 1 + (page_index * step)
            try:
                if not self.naver_client:
                    return collected
                results = self.naver_client.search_local(query, display=display, start=start)
            except httpx.HTTPStatusError as exc:
                warnings.append(
                    "NAVER_PAGE_FETCH_FAILED "
                    f"query={query} start={start} status={exc.response.status_code}"
                )
                break
            except httpx.HTTPError as exc:
                warnings.append(
                    "NAVER_PAGE_FETCH_FAILED "
                    f"query={query} start={start} error={type(exc).__name__}"
                )
                break
            if not results:
                break
            collected.extend(results)
        return collected

    def _collect_tour_keyword_pages(
        self,
        keyword: str,
        rows: int,
        pages: int,
        warnings: list[str],
    ) -> list[object]:
        collected: list[object] = []
        for page in range(1, max(pages, 1) + 1):
            try:
                if not self.tour_client:
                    return collected
                results = self.tour_client.search_keyword(keyword, rows=rows, page=page)
            except httpx.HTTPStatusError as exc:
                warnings.append(
                    "TOUR_API_KEYWORD_FETCH_FAILED "
                    f"keyword={keyword} page={page} status={exc.response.status_code}"
                )
                break
            except httpx.HTTPError as exc:
                warnings.append(
                    "TOUR_API_KEYWORD_FETCH_FAILED "
                    f"keyword={keyword} page={page} error={type(exc).__name__}"
                )
                break
            if not results:
                break
            collected.extend(results)
        return collected

    def _collect_tour_festival_pages(
        self,
        *,
        region_name: str,
        event_start_date: str,
        event_end_date: str | None,
        rows: int,
        pages: int,
        warnings: list[str],
    ) -> list[object]:
        collected: list[object] = []
        area_code, sigungu_code = _tour_region_codes(region_name)
        for page in range(1, max(pages, 1) + 1):
            try:
                if not self.tour_client:
                    return collected
                results = self.tour_client.search_festivals(
                    event_start_date=event_start_date,
                    event_end_date=event_end_date,
                    area_code=area_code,
                    sigungu_code=sigungu_code,
                    rows=rows,
                    page=page,
                )
            except httpx.HTTPStatusError as exc:
                warnings.append(
                    "TOUR_API_FESTIVAL_FETCH_FAILED "
                    "start="
                    f"{event_start_date} end={event_end_date or ''} "
                    f"page={page} status={exc.response.status_code}"
                )
                break
            except httpx.HTTPError as exc:
                warnings.append(
                    "TOUR_API_FESTIVAL_FETCH_FAILED "
                    "start="
                    f"{event_start_date} end={event_end_date or ''} "
                    f"page={page} error={type(exc).__name__}"
                )
                break
            if not results:
                break
            collected.extend(
                item
                for item in results
                if _is_place_in_region(_extract_address(item), region_name=region_name)
            )
        return collected

    def _collect_tour_stay_pages(
        self,
        *,
        rows: int,
        pages: int,
        warnings: list[str],
    ) -> list[object]:
        collected: list[object] = []
        for page in range(1, max(pages, 1) + 1):
            try:
                if not self.tour_client:
                    return collected
                results = self.tour_client.search_stays(rows=rows, page=page)
            except httpx.HTTPStatusError as exc:
                warnings.append(
                    f"TOUR_API_STAY_FETCH_FAILED page={page} status={exc.response.status_code}"
                )
                break
            except httpx.HTTPError as exc:
                warnings.append(
                    f"TOUR_API_STAY_FETCH_FAILED page={page} error={type(exc).__name__}"
                )
                break
            if not results:
                break
            collected.extend(results)
        return collected

    def _default_festival_start_date(self) -> str:
        return date.today().strftime("%Y0101")

    def _default_festival_end_date(self) -> str:
        return date.today().strftime("%Y1231")

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


def _tour_region_codes(region_name: str) -> tuple[int | None, int | None]:
    region_codes = {
        "공주": (34, 3),
        "부여": (34, 6),
        "천안": (34, 12),
        "아산": (34, 8),
        "청주": (33, None),
        "제천": (33, 13),
        "단양": (33, 11),
        "대전": (3, None),
        "세종": (8, None),
    }
    return region_codes.get(region_name, (None, None))


def _extract_address(item: object) -> str:
    data = _dump_item(item)
    if isinstance(data, dict):
        return str(data.get("addr1") or data.get("address") or "")
    return ""


def _is_place_in_region(address: str, *, region_name: str) -> bool:
    normalized = re.sub(r"\s+", "", address)
    if not normalized:
        return False
    region_patterns = {
        "공주": ["공주시", "충청남도공주시", "충남공주시"],
        "부여": ["부여군", "충청남도부여군", "충남부여군"],
        "천안": ["천안시", "충청남도천안시", "충남천안시"],
        "아산": ["아산시", "충청남도아산시", "충남아산시"],
        "청주": ["청주시", "충청북도청주시", "충북청주시"],
        "제천": ["제천시", "충청북도제천시", "충북제천시"],
        "단양": ["단양군", "충청북도단양군", "충북단양군"],
        "대전": ["대전", "대전광역시"],
        "세종": ["세종", "세종특별자치시"],
    }
    patterns = region_patterns.get(region_name, [region_name])
    return any(pattern in normalized for pattern in patterns)


def _filter_places_by_region(
    places: list[NormalizedPlace],
    *,
    region_name: str,
) -> list[NormalizedPlace]:
    in_region_candidates_by_key = {
        _variant_region_key(place): place
        for place in places
        if _has_recognizable_in_region_address(place, region_name=region_name)
    }
    filtered: list[NormalizedPlace] = []
    for place in places:
        if _should_exclude_place(place):
            continue
        if _has_recognizable_in_region_address(place, region_name=region_name):
            filtered.append(place)
            continue

        matching_in_region_candidate = in_region_candidates_by_key.get(_variant_region_key(place))
        if matching_in_region_candidate and _lacks_recognizable_address(place):
            rescued_place = place.model_copy(deep=True)
            if not rescued_place.road_address:
                rescued_place.road_address = matching_in_region_candidate.road_address
            if not rescued_place.address:
                rescued_place.address = matching_in_region_candidate.address
            filtered.append(rescued_place)
    return filtered


def _variant_region_key(place: NormalizedPlace) -> str:
    normalized_name = _normalize_place_text(place.name)
    rounded_latitude = round(place.latitude, 4)
    rounded_longitude = round(place.longitude, 4)
    return f"{normalized_name}:{rounded_latitude}:{rounded_longitude}"


def _normalize_place_text(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _has_recognizable_in_region_address(place: NormalizedPlace, *, region_name: str) -> bool:
    return _is_place_in_region(place.road_address or place.address, region_name=region_name)


def _lacks_recognizable_address(place: NormalizedPlace) -> bool:
    return not (place.road_address or place.address).strip()


def _should_exclude_place(place: NormalizedPlace) -> bool:
    raw_category = place.raw_category.replace(" ", "")
    name = place.name.replace(" ", "")

    excluded_category_keywords = (
        "전기차충전소",
        "주차장",
        "공영주차장",
        "단체,협회",
        "공사,공단",
        "연구소",
        "학교법인,재단",
        "부동산",
        "교량,다리",
        "건설자재",
        "시공업체",
        "슈퍼마켓",
        "화장실",
        "고속,시외버스정류장",
        "교차로",
        "입출구",
        "도로명칭",
        "매표소",
        "관광지관리운영",
        "건물관리사무소",
        "행정기관",
        "지방행정기관",
        "부속건물",
        "물류센터",
        "편의점",
        "약국",
        "의료기기판매",
        "주유소",
        "톨게이트",
        "고속도로IC",
    )
    excluded_name_keywords = (
        "전기차충전소",
        "주차장",
        "고객지원센터",
        "상인회",
        "협의회",
        "연구원",
        "연구소",
        "재단",
        "화장실",
        "정류장",
        "교차로",
        "입구",
        "매표소",
        "관리사무소",
        "치안센터",
        "119안전센터",
        "하수종말처리장",
    )

    if any(keyword in raw_category for keyword in excluded_category_keywords):
        return True
    if any(keyword in name for keyword in excluded_name_keywords):
        return True
    return False
