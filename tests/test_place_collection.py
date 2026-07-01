import json
import time

import httpx
import pytest

from app.clients.kakao_local_client import KakaoLocalClient
from app.clients.naver_local_client import NaverLocalClient
from app.clients.tour_api_client import TourApiClient
from app.schemas.place_source import (
    ExternalPlaceSource,
    NormalizedPlace,
    PlaceCategory,
    PlaceCollectionResult,
)
from app.services.place_collector import PlaceCollector
from app.services.place_deduplicator import deduplicate_places
from app.services.place_normalizer import (
    normalize_kakao_place,
    normalize_naver_place,
    normalize_tour_place,
)


def test_kakao_local_client_searches_keyword() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/local/search/keyword.json"
        assert request.url.params["query"] == "공주 관광지"
        assert request.url.params["page"] == "2"
        assert request.headers["Authorization"] == "KakaoAK kakao-test-key"
        return httpx.Response(
            200,
            json={
                "documents": [
                    {
                        "id": "kakao-1",
                        "place_name": "공산성",
                        "category_name": "여행 > 관광,명소 > 문화유적",
                        "category_group_code": "AT4",
                        "road_address_name": "충남 공주시 웅진로 280",
                        "address_name": "충남 공주시 금성동 53-51",
                        "x": "127.125997",
                        "y": "36.462293",
                        "phone": "041-856-7700",
                        "place_url": "https://place.map.kakao.com/1",
                    }
                ],
                "meta": {"total_count": 1, "is_end": True},
            },
        )

    client = KakaoLocalClient(
        api_key="kakao-test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    results = client.search_keyword("공주 관광지", size=3, page=2)

    assert len(results) == 1
    assert results[0].place_name == "공산성"
    assert results[0].longitude == 127.125997
    assert results[0].latitude == 36.462293


def test_naver_local_client_searches_local_places() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/search/local.json"
        assert request.url.params["query"] == "공주 카페"
        assert request.url.params["start"] == "6"
        assert request.headers["X-Naver-Client-Id"] == "naver-client-id"
        assert request.headers["X-Naver-Client-Secret"] == "naver-client-secret"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "title": "<b>루치아의뜰</b>",
                        "link": "https://example.com/place",
                        "category": "음식점>카페",
                        "description": "공주 한옥 카페",
                        "address": "충남 공주시 반죽동 100",
                        "roadAddress": "충남 공주시 웅진로 145",
                        "mapx": "1271234567",
                        "mapy": "361234567",
                    }
                ]
            },
        )

    client = NaverLocalClient(
        client_id="naver-client-id",
        client_secret="naver-client-secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    results = client.search_local("공주 카페", display=3, start=6)

    assert len(results) == 1
    assert results[0].title == "루치아의뜰"
    assert results[0].longitude == 127.1234567
    assert results[0].latitude == 36.1234567


def test_naver_local_client_retries_on_rate_limit_then_succeeds() -> None:
    attempts = {"count": 0}
    sleep_calls: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(429, request=request, json={"errorMessage": "rate limited"})
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "title": "<b>루치아의뜰</b>",
                        "link": "https://example.com/place",
                        "category": "음식점>카페",
                        "description": "공주 한옥 카페",
                        "address": "충남 공주시 반죽동 100",
                        "roadAddress": "충남 공주시 웅진로 145",
                        "mapx": "1271234567",
                        "mapy": "361234567",
                    }
                ]
            },
        )

    client = NaverLocalClient(
        client_id="naver-client-id",
        client_secret="naver-client-secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_attempts=2,
        retry_backoff_seconds=(0.0, 0.0),
        sleep_func=sleep_calls.append,
    )

    results = client.search_local("공주 카페", display=3, start=1)

    assert len(results) == 1
    assert attempts["count"] == 3
    assert sleep_calls == [0.0, 0.0]


def test_naver_local_client_raises_after_retry_budget_is_exhausted() -> None:
    attempts = {"count": 0}
    sleep_calls: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(429, request=request, json={"errorMessage": "rate limited"})

    client = NaverLocalClient(
        client_id="naver-client-id",
        client_secret="naver-client-secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_attempts=2,
        retry_backoff_seconds=(0.0, 0.0),
        sleep_func=sleep_calls.append,
    )

    try:
        client.search_local("공주 카페", display=3, start=1)
    except httpx.HTTPStatusError as exc:
        assert exc.response.status_code == 429
    else:
        raise AssertionError("Expected HTTPStatusError after exhausting retry budget")

    assert attempts["count"] == 3
    assert sleep_calls == [0.0, 0.0]


def test_naver_local_client_waits_between_sequential_requests() -> None:
    requests: list[int] = []
    sleep_calls: list[float] = []
    clock_values = iter([100.0, 100.2, 100.2, 101.0])

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(int(request.url.params["start"]))
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "title": "<b>루치아의뜰</b>",
                        "link": "https://example.com/place",
                        "category": "음식점>카페",
                        "description": "공주 한옥 카페",
                        "address": "충남 공주시 반죽동 100",
                        "roadAddress": "충남 공주시 웅진로 145",
                        "mapx": "1271234567",
                        "mapy": "361234567",
                    }
                ]
            },
        )

    client = NaverLocalClient(
        client_id="naver-client-id",
        client_secret="naver-client-secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        min_interval_seconds=1.0,
        sleep_func=sleep_calls.append,
        clock_func=lambda: next(clock_values),
    )

    client.search_local("공주 카페", display=3, start=1)
    client.search_local("공주 카페", display=3, start=6)

    assert requests == [1, 6]
    assert len(sleep_calls) == 1
    assert sleep_calls[0] == pytest.approx(0.8)


def test_tour_api_client_searches_keyword_places() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/B551011/KorService2/searchKeyword2"
        assert request.url.params["serviceKey"] == "tour-service-key"
        assert request.url.params["MobileOS"] == "ETC"
        assert request.url.params["MobileApp"] == "Tripio"
        assert request.url.params["_type"] == "json"
        assert request.url.params["pageNo"] == "2"
        assert request.url.params["keyword"] == "공주"
        assert request.url.params["numOfRows"] == "5"
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "0000", "resultMsg": "OK"},
                    "body": {
                        "totalCount": 1,
                        "items": {
                            "item": [
                                {
                                    "contentid": "126508",
                                    "contenttypeid": "12",
                                    "title": "공주 갑사 철당간",
                                    "addr1": "충청남도 공주시 계룡면 중장리",
                                    "addr2": "",
                                    "mapx": "127.1852806342",
                                    "mapy": "36.3646948037",
                                    "firstimage": "https://example.com/image.jpg",
                                    "tel": "041-000-0000",
                                    "cat1": "A02",
                                    "cat2": "A0201",
                                    "cat3": "A02010700",
                                }
                            ]
                        },
                    },
                }
            },
        )

    client = TourApiClient(
        service_key="tour-service-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    results = client.search_keyword("공주", rows=5, page=2)

    assert len(results) == 1
    assert results[0].title == "공주 갑사 철당간"
    assert results[0].content_id == "126508"
    assert results[0].longitude == 127.1852806342
    assert results[0].latitude == 36.3646948037


def test_tour_api_client_searches_festivals_with_event_dates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/B551011/KorService2/searchFestival2"
        assert request.url.params["pageNo"] == "3"
        assert request.url.params["eventStartDate"] == "20260601"
        assert request.url.params["eventEndDate"] == "20260630"
        assert request.url.params["areaCode"] == "34"
        assert request.url.params["sigunguCode"] == "3"
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "0000", "resultMsg": "OK"},
                    "body": {
                        "items": {
                            "item": {
                                "contentid": "festival-1",
                                "contenttypeid": "15",
                                "title": "공주 문화유산 야행",
                                "addr1": "충청남도 공주시 웅진로 280",
                                "mapx": "127.125997",
                                "mapy": "36.462293",
                                "eventstartdate": "20260610",
                                "eventenddate": "20260612",
                            }
                        },
                        "totalCount": 1,
                    },
                }
            },
        )

    client = TourApiClient(
        service_key="tour-service-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    results = client.search_festivals(
        event_start_date="20260601",
        event_end_date="20260630",
        area_code=34,
        sigungu_code=3,
        page=3,
    )

    assert len(results) == 1
    assert results[0].title == "공주 문화유산 야행"
    assert results[0].event_start_date == "20260610"
    assert results[0].event_end_date == "20260612"


def test_tour_api_client_searches_stays_with_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/B551011/KorService2/searchStay2"
        assert request.url.params["pageNo"] == "2"
        assert request.url.params["numOfRows"] == "10"
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "0000", "resultMsg": "OK"},
                    "body": {
                        "items": {
                            "item": {
                                "contentid": "stay-1",
                                "contenttypeid": "32",
                                "title": "공주 한옥 스테이",
                                "addr1": "충청남도 공주시 웅진로 10",
                                "mapx": "127.120000",
                                "mapy": "36.460000",
                            }
                        },
                        "totalCount": 1,
                    },
                }
            },
        )

    client = TourApiClient(
        service_key="tour-service-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    results = client.search_stays(rows=10, page=2)

    assert len(results) == 1
    assert results[0].title == "공주 한옥 스테이"


def test_tour_api_client_returns_empty_list_when_items_is_blank_string() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "0000", "resultMsg": "OK"},
                    "body": {
                        "items": "",
                        "totalCount": 0,
                    },
                }
            },
        )

    client = TourApiClient(
        service_key="tour-service-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    results = client.search_keyword("공주", rows=10, page=2)

    assert results == []


def test_normalizes_kakao_and_naver_places() -> None:
    kakao = normalize_kakao_place(
        {
            "id": "kakao-1",
            "place_name": "공산성",
            "category_name": "여행 > 관광,명소 > 문화유적",
            "category_group_code": "AT4",
            "road_address_name": "충남 공주시 웅진로 280",
            "address_name": "충남 공주시 금성동 53-51",
            "x": "127.125997",
            "y": "36.462293",
            "phone": "041-856-7700",
            "place_url": "https://place.map.kakao.com/1",
        },
        region_name="공주",
        query="공주 관광지",
    )

    naver = normalize_naver_place(
        {
            "title": "<b>공주산성시장</b>",
            "link": "https://example.com/market",
            "category": "쇼핑,유통>시장",
            "description": "공주 대표 전통시장",
            "address": "충남 공주시 산성동 120",
            "roadAddress": "충남 공주시 용당길 22",
            "mapx": "1271240000",
            "mapy": "364620000",
        },
        region_name="공주",
        query="공주 시장",
    )

    assert kakao.source == ExternalPlaceSource.KAKAO
    assert kakao.category == PlaceCategory.TOURIST_ATTRACTION
    assert kakao.tags == ["관광지", "문화유적"]
    assert naver.source == ExternalPlaceSource.NAVER
    assert naver.name == "공주산성시장"
    assert naver.category == PlaceCategory.MARKET
    assert naver.tags == ["시장"]


def test_place_collection_result_defaults_quality_summary_for_direct_construction() -> None:
    result = PlaceCollectionResult(
        region_name="공주",
        queries=["공주 관광지"],
        processed_places=[],
    )

    assert result.quality_summary.input_count == 0
    assert result.quality_summary.kept_count == 0
    assert result.quality_summary.filtered_count == 0
    assert result.quality_summary.reclassified_count == 0


def test_normalizes_etc_candidates_into_restaurant_activity_and_culture() -> None:
    naver_restaurant = normalize_naver_place(
        {
            "title": "피탕김탕",
            "link": "",
            "category": "중식>중식당",
            "description": "",
            "address": "충청남도 공주시 한적2길 47-5",
            "roadAddress": "충청남도 공주시 한적2길 47-5",
            "mapx": "1271396164",
            "mapy": "364782512",
        },
        region_name="공주",
        query="공주 맛집",
    )
    kakao_activity = normalize_kakao_place(
        {
            "id": "kakao-activity",
            "place_name": "백제문화체험",
            "category_name": "여행 > 체험여행",
            "category_group_code": "",
            "road_address_name": "충남 공주시 웅진로 280",
            "address_name": "충남 공주시 금성동 53-51",
            "x": "127.126790",
            "y": "36.462950",
            "phone": "",
            "place_url": "https://place.map.kakao.com/activity",
        },
        region_name="공주",
        query="공주 체험",
    )
    kakao_culture = normalize_kakao_place(
        {
            "id": "kakao-culture",
            "place_name": "백제문화전당",
            "category_name": "문화,예술 > 문화시설",
            "category_group_code": "",
            "road_address_name": "충남 공주시 고마나루길 73",
            "address_name": "충남 공주시 웅진동 337",
            "x": "127.110000",
            "y": "36.460000",
            "phone": "",
            "place_url": "https://place.map.kakao.com/culture",
        },
        region_name="공주",
        query="공주 문화시설",
    )
    kakao_park = normalize_kakao_place(
        {
            "id": "kakao-park",
            "place_name": "공주산성시장 문화공원",
            "category_name": "여행 > 공원",
            "category_group_code": "",
            "road_address_name": "충남 공주시 산성동 181-82",
            "address_name": "충남 공주시 산성동 181-82",
            "x": "127.122980",
            "y": "36.457149",
            "phone": "",
            "place_url": "https://place.map.kakao.com/park",
        },
        region_name="공주",
        query="공주 공원",
    )
    naver_temple = normalize_naver_place(
        {
            "title": "동학사",
            "link": "",
            "category": "불교>절,사찰",
            "description": "",
            "address": "충청남도 공주시 반포면 동학사1로 462",
            "roadAddress": "충청남도 공주시 반포면 동학사1로 462",
            "mapx": "1272610000",
            "mapy": "363650000",
        },
        region_name="공주",
        query="공주 사찰",
    )
    naver_culture_center = normalize_naver_place(
        {
            "title": "공주시민문화센터",
            "link": "",
            "category": "교육,학문>문화센터",
            "description": "",
            "address": "충청남도 공주시 전막3길 27",
            "roadAddress": "충청남도 공주시 전막3길 27",
            "mapx": "1271300000",
            "mapy": "364690000",
        },
        region_name="공주",
        query="공주 문화센터",
    )
    naver_market = normalize_naver_place(
        {
            "title": "공주시우수농특산물판매장",
            "link": "",
            "category": "쇼핑,유통>특산물,관광민예품",
            "description": "",
            "address": "충청남도 공주시 반포면 서덕산길 3-2",
            "roadAddress": "충청남도 공주시 반포면 서덕산길 3-2",
            "mapx": "1271060000",
            "mapy": "364620000",
        },
        region_name="공주",
        query="공주 특산물",
    )
    naver_craft = normalize_naver_place(
        {
            "title": "수다도예공방",
            "link": "",
            "category": "생활,편의>공방",
            "description": "",
            "address": "충청남도 공주시 봉황산1길 10",
            "roadAddress": "충청남도 공주시 봉황산1길 10",
            "mapx": "1271200000",
            "mapy": "364510000",
        },
        region_name="공주",
        query="공주 공방",
    )
    naver_activity = normalize_naver_place(
        {
            "title": "백제체육관",
            "link": "",
            "category": "스포츠,오락>실내체육관",
            "description": "",
            "address": "충청남도 공주시 고마나루길 51-14",
            "roadAddress": "충청남도 공주시 고마나루길 51-14",
            "mapx": "1271110000",
            "mapy": "364600000",
        },
        region_name="공주",
        query="공주 체육관",
    )
    naver_pojangmacha = normalize_naver_place(
        {
            "title": "오는정가는정",
            "link": "",
            "category": "술집>포장마차",
            "description": "",
            "address": "충청남도 공주시 느티나무길 4-1",
            "roadAddress": "충청남도 공주시 느티나무길 4-1",
            "mapx": "1271230000",
            "mapy": "364520000",
        },
        region_name="공주",
        query="공주 포장마차",
    )
    naver_temple_stay = normalize_naver_place(
        {
            "title": "마곡사 템플스테이",
            "link": "",
            "category": "문화,예술 > 종교 > 불교 > 템플스테이",
            "description": "",
            "address": "충청남도 공주시 사곡면 마곡사로 991",
            "roadAddress": "충청남도 공주시 사곡면 마곡사로 991",
            "mapx": "1270080000",
            "mapy": "365570000",
        },
        region_name="공주",
        query="공주 템플스테이",
    )

    assert naver_restaurant.category == PlaceCategory.RESTAURANT
    assert kakao_activity.category == PlaceCategory.ACTIVITY
    assert kakao_culture.category == PlaceCategory.CULTURE
    assert kakao_park.category == PlaceCategory.TOURIST_ATTRACTION
    assert naver_temple.category == PlaceCategory.TOURIST_ATTRACTION
    assert naver_culture_center.category == PlaceCategory.CULTURE
    assert naver_market.category == PlaceCategory.MARKET
    assert naver_craft.category == PlaceCategory.CULTURE
    assert naver_activity.category == PlaceCategory.ACTIVITY
    assert naver_pojangmacha.category == PlaceCategory.RESTAURANT
    assert naver_temple_stay.category == PlaceCategory.LODGING


def test_place_collector_filters_out_of_region_festivals(tmp_path) -> None:
    class FakeKakaoClient:
        def search_keyword(
            self,
            query: str,
            *,
            size: int = 15,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return []

    class FakeNaverClient:
        def search_local(
            self,
            query: str,
            *,
            display: int = 5,
            start: int = 1,
            sort: str = "random",
        ) -> list[dict[str, object]]:
            return []

    class FakeTourClient:
        def search_keyword(
            self,
            keyword: str,
            *,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return []

        def search_festivals(
            self,
            *,
            event_start_date: str,
            event_end_date: str | None = None,
            area_code: int | None = None,
            sigungu_code: int | None = None,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            assert area_code == 34
            assert sigungu_code == 3
            return [
                {
                    "contentid": "festival-gongju",
                    "contenttypeid": "15",
                    "title": "공주 문화유산 야행",
                    "addr1": "충청남도 공주시 웅진로 280",
                    "mapx": "127.125997",
                    "mapy": "36.462293",
                    "eventstartdate": "20261001",
                    "eventenddate": "20261003",
                },
                {
                    "contentid": "festival-seoul",
                    "contenttypeid": "15",
                    "title": "강남 미디어 윈터페스타",
                    "addr1": "서울특별시 강남구 영동대로 511",
                    "mapx": "127.059023",
                    "mapy": "37.511899",
                    "eventstartdate": "20261002",
                    "eventenddate": "20261004",
                },
            ]

        def search_stays(
            self,
            *,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return []

    collector = PlaceCollector(
        kakao_client=FakeKakaoClient(),
        naver_client=FakeNaverClient(),
        tour_client=FakeTourClient(),
        output_root=tmp_path,
    )

    result = collector.collect(
        region_name="공주",
        queries=["공주 관광지"],
        tour_keywords=["공주"],
        include_tour_festivals=True,
        festival_start_date="20261001",
        festival_end_date="20261031",
    )

    names = {place.name for place in result.processed_places}
    assert "공주 문화유산 야행" in names
    assert "강남 미디어 윈터페스타" not in names


def test_normalizes_tour_api_places_by_content_type() -> None:
    attraction = normalize_tour_place(
        {
            "contentid": "126508",
            "contenttypeid": "12",
            "title": "공주 갑사 철당간",
            "addr1": "충청남도 공주시 계룡면 중장리",
            "mapx": "127.1852806342",
            "mapy": "36.3646948037",
            "firstimage": "https://example.com/image.jpg",
            "tel": "041-000-0000",
        },
        region_name="공주",
        query="공주",
    )
    festival = normalize_tour_place(
        {
            "contentid": "festival-1",
            "contenttypeid": "15",
            "title": "공주 문화유산 야행",
            "addr1": "충청남도 공주시 웅진로 280",
            "mapx": "127.125997",
            "mapy": "36.462293",
            "eventstartdate": "20260610",
            "eventenddate": "20260612",
        },
        region_name="공주",
        query="202606 축제",
    )

    assert attraction.source == ExternalPlaceSource.TOUR_API
    assert attraction.category == PlaceCategory.TOURIST_ATTRACTION
    assert attraction.source_place_id == "126508"
    assert attraction.image_url == "https://example.com/image.jpg"
    assert attraction.tags == ["관광지"]
    assert festival.category == PlaceCategory.ACTIVITY
    assert festival.tags == ["체험/액티비티", "축제"]


def test_normalizes_kakao_tourist_place_without_category_group_code() -> None:
    place = normalize_kakao_place(
        {
            "id": "kakao-2",
            "place_name": "공주한옥마을",
            "category_name": "여행 > 관광,명소",
            "category_group_code": "",
            "road_address_name": "충남 공주시 관광단지길 12",
            "address_name": "충남 공주시 웅진동 337",
            "x": "127.119725",
            "y": "36.462943",
            "phone": "",
            "place_url": "https://place.map.kakao.com/2",
        },
        region_name="공주",
        query="공주 관광지",
    )

    assert place.category == PlaceCategory.TOURIST_ATTRACTION
    assert place.tags == ["관광지"]


def test_deduplicates_places_by_name_and_address() -> None:
    places = [
        NormalizedPlace(
            source=ExternalPlaceSource.KAKAO,
            source_place_id="kakao-1",
            name="공산성",
            region_name="공주",
            address="충남 공주시 웅진로 280",
            latitude=36.462293,
            longitude=127.125997,
            category=PlaceCategory.TOURIST_ATTRACTION,
            source_query="공주 관광지",
        ),
        NormalizedPlace(
            source=ExternalPlaceSource.NAVER,
            source_place_id="https://example.com/place",
            name="공산성",
            region_name="공주",
            address="충남 공주시 웅진로 280",
            latitude=36.462294,
            longitude=127.125998,
            category=PlaceCategory.TOURIST_ATTRACTION,
            source_query="공주 명소",
        ),
    ]

    deduplicated = deduplicate_places(places)

    assert len(deduplicated) == 1
    assert deduplicated[0].sources == [ExternalPlaceSource.KAKAO, ExternalPlaceSource.NAVER]
    assert deduplicated[0].source_place_ids == ["kakao-1", "https://example.com/place"]


def test_place_collector_writes_raw_and_processed_json(tmp_path) -> None:
    class FakeKakaoClient:
        def search_keyword(
            self,
            query: str,
            *,
            size: int = 15,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return [
                {
                    "id": "kakao-1",
                    "place_name": "공산성",
                    "category_name": "여행 > 관광,명소 > 문화유적",
                    "category_group_code": "AT4",
                    "road_address_name": "충남 공주시 웅진로 280",
                    "address_name": "충남 공주시 금성동 53-51",
                    "x": "127.125997",
                    "y": "36.462293",
                    "phone": "",
                    "place_url": "https://place.map.kakao.com/1",
                }
            ]

    class FakeNaverClient:
        def search_local(
            self,
            query: str,
            *,
            display: int = 5,
            start: int = 1,
            sort: str = "random",
        ) -> list[dict[str, object]]:
            return [
                {
                    "title": "<b>공산성</b>",
                    "link": "https://example.com/place",
                    "category": "여행,명소>문화유적",
                    "description": "공주 대표 관광지",
                    "address": "충남 공주시 금성동 53-51",
                    "roadAddress": "충남 공주시 웅진로 280",
                    "mapx": "1271259970",
                    "mapy": "364622930",
                }
            ]

    class FakeTourClient:
        def search_keyword(
            self,
            keyword: str,
            *,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return [
                {
                    "contentid": "126508",
                    "contenttypeid": "12",
                    "title": "공산성",
                    "addr1": "충남 공주시 웅진로 280",
                    "mapx": "127.125997",
                    "mapy": "36.462293",
                    "firstimage": "https://example.com/gongsanseong.jpg",
                }
            ]

    collector = PlaceCollector(
        kakao_client=FakeKakaoClient(),
        naver_client=FakeNaverClient(),
        tour_client=FakeTourClient(),
        output_root=tmp_path,
    )

    result = collector.collect(region_name="공주", queries=["공주 관광지"], tour_keywords=["공주"])

    assert len(result.processed_places) == 1
    assert (tmp_path / "raw" / "kakao" / "gongju_gongju-tourist-attraction.json").exists()
    assert (tmp_path / "raw" / "naver" / "gongju_gongju-tourist-attraction.json").exists()
    assert (tmp_path / "raw" / "tour_api" / "gongju_gongju.json").exists()
    processed_path = tmp_path / "processed" / "gongju_places.json"
    assert processed_path.exists()

    saved = json.loads(processed_path.read_text(encoding="utf-8"))
    assert saved[0]["name"] == "공산성"
    assert saved[0]["sources"] == ["KAKAO", "NAVER", "TOUR_API"]
    assert result.quality_summary.input_count == 1
    assert result.quality_summary.kept_count == 1
    assert result.quality_summary.filtered_count == 0
    assert result.quality_summary.reclassified_count == 0


def test_place_collector_collects_multiple_pages_and_tour_expansions(tmp_path) -> None:
    class FakeKakaoClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def search_keyword(
            self,
            query: str,
            *,
            size: int = 15,
            page: int = 1,
        ) -> list[dict[str, object]]:
            self.calls.append((query, page))
            if page == 1:
                return [
                    {
                        "id": "kakao-1",
                        "place_name": "공산성",
                        "category_name": "여행 > 관광,명소 > 문화유적",
                        "category_group_code": "AT4",
                        "road_address_name": "충남 공주시 웅진로 280",
                        "address_name": "충남 공주시 금성동 53-51",
                        "x": "127.125997",
                        "y": "36.462293",
                        "phone": "",
                        "place_url": "https://place.map.kakao.com/1",
                    }
                ]
            return [
                {
                    "id": "kakao-2",
                    "place_name": "무령왕릉",
                    "category_name": "여행 > 관광,명소 > 문화유적",
                    "category_group_code": "AT4",
                    "road_address_name": "충남 공주시 왕릉로 37",
                    "address_name": "충남 공주시 웅진동 57",
                    "x": "127.112523",
                    "y": "36.460573",
                    "phone": "",
                    "place_url": "https://place.map.kakao.com/2",
                }
            ]

    class FakeNaverClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def search_local(
            self,
            query: str,
            *,
            display: int = 5,
            start: int = 1,
            sort: str = "random",
        ) -> list[dict[str, object]]:
            self.calls.append((query, start))
            if start == 1:
                return [
                    {
                        "title": "<b>공주산성시장</b>",
                        "link": "https://example.com/market",
                        "category": "쇼핑,유통>시장",
                        "description": "공주 대표 전통시장",
                        "address": "충남 공주시 산성동 120",
                        "roadAddress": "충남 공주시 용당길 22",
                        "mapx": "1271240000",
                        "mapy": "364620000",
                    }
                ]
            return []

    class FakeTourClient:
        def __init__(self) -> None:
            self.keyword_calls: list[tuple[str, int]] = []
            self.festival_calls: list[int] = []
            self.stay_calls: list[int] = []

        def search_keyword(
            self,
            keyword: str,
            *,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            self.keyword_calls.append((keyword, page))
            if page == 1:
                return [
                    {
                        "contentid": "tour-1",
                        "contenttypeid": "12",
                        "title": "공주 고마나루",
                        "addr1": "충남 공주시 백제큰길 2045",
                        "mapx": "127.106345",
                        "mapy": "36.468708",
                    }
                ]
            return []

        def search_festivals(
            self,
            *,
            event_start_date: str,
            event_end_date: str | None = None,
            area_code: int | None = None,
            sigungu_code: int | None = None,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            self.festival_calls.append(page)
            assert area_code == 34
            assert sigungu_code == 3
            if page == 1:
                return [
                    {
                        "contentid": "festival-1",
                        "contenttypeid": "15",
                        "title": "공주 문화유산 야행",
                        "addr1": "충남 공주시 웅진로 280",
                        "mapx": "127.125997",
                        "mapy": "36.462293",
                        "eventstartdate": "20261001",
                        "eventenddate": "20261003",
                    }
                ]
            return []

        def search_stays(
            self,
            *,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            self.stay_calls.append(page)
            if page == 1:
                return [
                    {
                        "contentid": "stay-1",
                        "contenttypeid": "32",
                        "title": "공주 한옥 스테이",
                        "addr1": "충남 공주시 미나리3길 12-4",
                        "mapx": "127.122299",
                        "mapy": "36.463384",
                    }
                ]
            return []

    kakao = FakeKakaoClient()
    naver = FakeNaverClient()
    tour = FakeTourClient()
    collector = PlaceCollector(
        kakao_client=kakao,
        naver_client=naver,
        tour_client=tour,
        output_root=tmp_path,
    )

    result = collector.collect(
        region_name="공주",
        queries=["공주 관광지"],
        tour_keywords=["공주"],
        kakao_pages=2,
        naver_pages=2,
        tour_pages=2,
        include_tour_festivals=True,
        include_tour_stays=True,
        festival_start_date="20261001",
        festival_end_date="20261031",
    )

    names = {place.name for place in result.processed_places}
    assert {"공산성", "무령왕릉", "공주산성시장", "공주 고마나루", "공주 문화유산 야행", "공주 한옥 스테이"} <= names
    assert kakao.calls == [("공주 관광지", 1), ("공주 관광지", 2)]
    assert naver.calls == [("공주 관광지", 1), ("공주 관광지", 6)]
    assert tour.keyword_calls == [("공주", 1), ("공주", 2)]
    assert tour.festival_calls == [1, 2]
    assert tour.stay_calls == [1, 2]


def test_place_collector_collects_tour_festivals_and_stays_without_tour_keywords(tmp_path) -> None:
    class FakeTourClient:
        def __init__(self) -> None:
            self.keyword_calls: list[tuple[str, int]] = []
            self.festival_calls: list[int] = []
            self.stay_calls: list[int] = []

        def search_keyword(
            self,
            keyword: str,
            *,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            self.keyword_calls.append((keyword, page))
            return []

        def search_festivals(
            self,
            *,
            event_start_date: str,
            event_end_date: str | None = None,
            area_code: int | None = None,
            sigungu_code: int | None = None,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            self.festival_calls.append(page)
            if page > 1:
                return []
            return [
                {
                    "contentid": "festival-1",
                    "contenttypeid": "15",
                    "title": "공주 문화유산 야행",
                    "addr1": "충남 공주시 웅진로 280",
                    "mapx": "127.125997",
                    "mapy": "36.462293",
                    "eventstartdate": "20261001",
                    "eventenddate": "20261003",
                }
            ]

        def search_stays(
            self,
            *,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            self.stay_calls.append(page)
            if page > 1:
                return []
            return [
                {
                    "contentid": "stay-1",
                    "contenttypeid": "32",
                    "title": "공주 한옥 스테이",
                    "addr1": "충남 공주시 미나리3길 12-4",
                    "mapx": "127.122299",
                    "mapy": "36.463384",
                }
            ]

    tour = FakeTourClient()
    collector = PlaceCollector(
        kakao_client=None,
        naver_client=None,
        tour_client=tour,
        output_root=tmp_path,
    )

    result = collector.collect(
        region_name="공주",
        queries=[],
        tour_keywords=None,
        include_tour_festivals=True,
        include_tour_stays=True,
        festival_start_date="20261001",
        festival_end_date="20261031",
        tour_pages=2,
    )

    assert {place.name for place in result.processed_places} == {"공주 문화유산 야행", "공주 한옥 스테이"}
    assert tour.keyword_calls == []
    assert tour.festival_calls == [1, 2]
    assert tour.stay_calls == [1, 2]


def test_place_collector_filters_out_of_region_places_from_all_sources(tmp_path) -> None:
    class FakeKakaoClient:
        def search_keyword(
            self,
            query: str,
            *,
            size: int = 15,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return [
                {
                    "id": "kakao-gongju",
                    "place_name": "공산성",
                    "category_name": "여행 > 관광,명소 > 문화유적",
                    "category_group_code": "AT4",
                    "road_address_name": "충남 공주시 웅진로 280",
                    "address_name": "충남 공주시 금성동 53-51",
                    "x": "127.125997",
                    "y": "36.462293",
                    "phone": "",
                    "place_url": "https://place.map.kakao.com/1",
                },
                {
                    "id": "kakao-sejong",
                    "place_name": "대평시장",
                    "category_name": "가정,생활 > 시장",
                    "category_group_code": "AT4",
                    "road_address_name": "세종특별자치시 금남면 대평시장1길 17-2",
                    "address_name": "세종특별자치시 금남면 대평리",
                    "x": "127.282060",
                    "y": "36.467267",
                    "phone": "",
                    "place_url": "https://place.map.kakao.com/2",
                },
            ]

    class FakeNaverClient:
        def search_local(
            self,
            query: str,
            *,
            display: int = 5,
            start: int = 1,
            sort: str = "random",
        ) -> list[dict[str, object]]:
            return [
                {
                    "title": "<b>루치아의 뜰</b>",
                    "link": "https://example.com/gongju-cafe",
                    "category": "카페,디저트>차",
                    "description": "공주 한옥 카페",
                    "address": "충청남도 공주시 웅진로 145-8",
                    "roadAddress": "충청남도 공주시 웅진로 145-8",
                    "mapx": "1271237815",
                    "mapy": "364537678",
                },
                {
                    "title": "<b>차전장군 노국공주축제</b>",
                    "link": "https://example.com/andong-festival",
                    "category": "관람,체험>축제",
                    "description": "안동 축제",
                    "address": "경상북도 안동시 서동문로 193",
                    "roadAddress": "경상북도 안동시 서동문로 193",
                    "mapx": "1287291000",
                    "mapy": "366823000",
                },
            ]

    class FakeTourClient:
        def search_keyword(
            self,
            keyword: str,
            *,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return [
                {
                    "contentid": "tour-gongju",
                    "contenttypeid": "12",
                    "title": "공주 고마나루",
                    "addr1": "충남 공주시 백제큰길 2045",
                    "mapx": "127.106345",
                    "mapy": "36.468708",
                },
                {
                    "contentid": "tour-buyeo",
                    "contenttypeid": "12",
                    "title": "부여 궁남지",
                    "addr1": "충남 부여군 부여읍 궁남로 52",
                    "mapx": "126.910000",
                    "mapy": "36.275000",
                },
            ]

        def search_festivals(
            self,
            *,
            event_start_date: str,
            event_end_date: str | None = None,
            area_code: int | None = None,
            sigungu_code: int | None = None,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return []

        def search_stays(
            self,
            *,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return [
                {
                    "contentid": "stay-gongju",
                    "contenttypeid": "32",
                    "title": "공주 한옥 스테이",
                    "addr1": "충남 공주시 미나리3길 12-4",
                    "mapx": "127.122299",
                    "mapy": "36.463384",
                },
                {
                    "contentid": "stay-daejeon",
                    "contenttypeid": "32",
                    "title": "대전 시티 호텔",
                    "addr1": "대전광역시 중구 중앙로 100",
                    "mapx": "127.423000",
                    "mapy": "36.325000",
                },
            ]

    collector = PlaceCollector(
        kakao_client=FakeKakaoClient(),
        naver_client=FakeNaverClient(),
        tour_client=FakeTourClient(),
        output_root=tmp_path,
    )

    result = collector.collect(
        region_name="공주",
        queries=["공주 관광지"],
        tour_keywords=["공주"],
        include_tour_stays=True,
    )

    names = {place.name for place in result.processed_places}
    assert names == {"공산성", "루치아의 뜰", "공주 고마나루", "공주 한옥 스테이"}


def test_place_collector_keeps_out_of_region_variant_when_matching_in_region_duplicate(tmp_path) -> None:
    class FakeKakaoClient:
        def search_keyword(
            self,
            query: str,
            *,
            size: int = 15,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return [
                {
                    "id": "kakao-1",
                    "place_name": "공산성",
                    "category_name": "여행 > 관광,명소 > 문화유적",
                    "category_group_code": "AT4",
                    "road_address_name": "",
                    "address_name": "",
                    "x": "127.125997",
                    "y": "36.462293",
                    "phone": "",
                    "place_url": "https://place.map.kakao.com/1",
                }
            ]

    class FakeNaverClient:
        def search_local(
            self,
            query: str,
            *,
            display: int = 5,
            start: int = 1,
            sort: str = "random",
        ) -> list[dict[str, object]]:
            return [
                {
                    "title": "<b>공산성</b>",
                    "link": "https://example.com/gongsanseong",
                    "category": "여행,명소>문화유적",
                    "description": "공주 대표 관광지",
                    "address": "충남 공주시 금성동 53-51",
                    "roadAddress": "충청남도 공주시 웅진로 280",
                    "mapx": "1271259970",
                    "mapy": "364622930",
                }
            ]

    collector = PlaceCollector(
        kakao_client=FakeKakaoClient(),
        naver_client=FakeNaverClient(),
        output_root=tmp_path,
    )

    result = collector.collect(region_name="공주", queries=["공주 관광지"], tour_keywords=None)

    assert len(result.processed_places) == 1
    place = result.processed_places[0]
    assert place.name == "공산성"
    assert place.sources == [ExternalPlaceSource.KAKAO, ExternalPlaceSource.NAVER]
    assert place.source_place_ids == ["kakao-1", "https://example.com/gongsanseong"]


def test_place_collector_does_not_rescue_explicit_out_of_region_duplicate_variant(tmp_path) -> None:
    class FakeKakaoClient:
        def search_keyword(
            self,
            query: str,
            *,
            size: int = 15,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return [
                {
                    "id": "kakao-1",
                    "place_name": "공산성",
                    "category_name": "여행 > 관광,명소 > 문화유적",
                    "category_group_code": "AT4",
                    "road_address_name": "세종특별자치시 금남면 허울뿐길 1",
                    "address_name": "세종특별자치시 금남면 허울뿐길 1",
                    "x": "127.125997",
                    "y": "36.462293",
                    "phone": "",
                    "place_url": "https://place.map.kakao.com/1",
                }
            ]

    class FakeNaverClient:
        def search_local(
            self,
            query: str,
            *,
            display: int = 5,
            start: int = 1,
            sort: str = "random",
        ) -> list[dict[str, object]]:
            return [
                {
                    "title": "<b>공산성</b>",
                    "link": "https://example.com/gongsanseong",
                    "category": "여행,명소>문화유적",
                    "description": "공주 대표 관광지",
                    "address": "충남 공주시 금성동 53-51",
                    "roadAddress": "충청남도 공주시 웅진로 280",
                    "mapx": "1271259970",
                    "mapy": "364622930",
                }
            ]

    collector = PlaceCollector(
        kakao_client=FakeKakaoClient(),
        naver_client=FakeNaverClient(),
        output_root=tmp_path,
    )

    result = collector.collect(region_name="공주", queries=["공주 관광지"], tour_keywords=None)

    assert len(result.processed_places) == 1
    place = result.processed_places[0]
    assert place.sources == [ExternalPlaceSource.NAVER]
    assert place.source_place_ids == ["https://example.com/gongsanseong"]


def test_place_collector_quality_summary_starts_after_collector_exclusions(tmp_path) -> None:
    class FakeKakaoClient:
        def search_keyword(
            self,
            query: str,
            *,
            size: int = 15,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return [
                {
                    "id": "kakao-parking",
                    "place_name": "유구전통시장 공영주차장",
                    "category_name": "교통,수송 > 교통시설 > 주차장 > 공영주차장",
                    "category_group_code": "",
                    "road_address_name": "충남 공주시 유구읍 석남리 275-11",
                    "address_name": "충남 공주시 유구읍 석남리 275-11",
                    "x": "126.951000",
                    "y": "36.553000",
                    "phone": "",
                    "place_url": "https://place.map.kakao.com/parking",
                },
                {
                    "id": "kakao-museum",
                    "place_name": "공주역사박물관",
                    "category_name": "문화,예술 > 박물관",
                    "category_group_code": "",
                    "road_address_name": "충남 공주시 번영1로 97-12",
                    "address_name": "충남 공주시 번영1로 97-12",
                    "x": "127.130000",
                    "y": "36.469000",
                    "phone": "",
                    "place_url": "https://place.map.kakao.com/museum",
                },
            ]

    class FakeNaverClient:
        def search_local(
            self,
            query: str,
            *,
            display: int = 5,
            start: int = 1,
            sort: str = "random",
        ) -> list[dict[str, object]]:
            return [
                {
                    "title": "동학사",
                    "link": "",
                    "category": "불교>절,사찰",
                    "description": "",
                    "address": "충청남도 공주시 반포면 동학사1로 462",
                    "roadAddress": "충청남도 공주시 반포면 동학사1로 462",
                    "mapx": "1272610000",
                    "mapy": "363650000",
                },
                {
                    "title": "충청안전체험교육장 전기차충전소",
                    "link": "",
                    "category": "교통,수송>자동차>전기차 충전소",
                    "description": "",
                    "address": "충청남도 공주시 반포면 금벽로 1714-77",
                    "roadAddress": "충청남도 공주시 반포면 금벽로 1714-77",
                    "mapx": "1272400000",
                    "mapy": "363620000",
                },
            ]

    collector = PlaceCollector(
        kakao_client=FakeKakaoClient(),
        naver_client=FakeNaverClient(),
        output_root=tmp_path,
    )

    result = collector.collect(region_name="공주", queries=["공주 문화"], tour_keywords=None)

    names = {place.name for place in result.processed_places}
    assert names == {"공주역사박물관", "동학사"}
    categories = {place.name: place.category for place in result.processed_places}
    assert categories["공주역사박물관"] == PlaceCategory.CULTURE
    assert categories["동학사"] == PlaceCategory.TOURIST_ATTRACTION
    # Collector-side exclusions run before quality refinement, so the summary starts
    # from the surviving candidates rather than all raw fetched rows.
    assert result.quality_summary.input_count == 2
    assert result.quality_summary.kept_count == 2
    assert result.quality_summary.filtered_count == 0
    assert result.quality_summary.reclassified_count == 1

    processed_path = tmp_path / "processed" / "gongju_places.json"
    saved = json.loads(processed_path.read_text(encoding="utf-8"))
    assert {place["name"] for place in saved} == {"공주역사박물관", "동학사"}


def test_place_collector_promotes_market_activity_and_culture_candidates(tmp_path) -> None:
    class FakeKakaoClient:
        def search_keyword(
            self,
            query: str,
            *,
            size: int = 15,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return [
                {
                    "id": "kakao-market",
                    "place_name": "공주알밤한우 산성시장점",
                    "category_name": "가정,생활 > 식품판매 > 정육점",
                    "category_group_code": "",
                    "road_address_name": "충남 공주시 산성시장1길 112",
                    "address_name": "충남 공주시 산성시장1길 112",
                    "x": "127.123000",
                    "y": "36.458000",
                    "phone": "",
                    "place_url": "https://place.map.kakao.com/market",
                },
                {
                    "id": "kakao-culture",
                    "place_name": "로컬공방",
                    "category_name": "생활,편의 > 공방",
                    "category_group_code": "",
                    "road_address_name": "충남 공주시 향교1길 20",
                    "address_name": "충남 공주시 향교1길 20",
                    "x": "127.124000",
                    "y": "36.452000",
                    "phone": "",
                    "place_url": "https://place.map.kakao.com/craft",
                },
                {
                    "id": "kakao-noise",
                    "place_name": "공산성 매표소",
                    "category_name": "서비스,산업 > 관리,운영 > 매표소",
                    "category_group_code": "",
                    "road_address_name": "충남 공주시 금성동 66-6",
                    "address_name": "충남 공주시 금성동 66-6",
                    "x": "127.126000",
                    "y": "36.463000",
                    "phone": "",
                    "place_url": "https://place.map.kakao.com/ticket",
                },
            ]

    class FakeNaverClient:
        def search_local(
            self,
            query: str,
            *,
            display: int = 5,
            start: int = 1,
            sort: str = "random",
        ) -> list[dict[str, object]]:
            return [
                {
                    "title": "백제체육관",
                    "link": "",
                    "category": "스포츠,오락>실내체육관",
                    "description": "",
                    "address": "충청남도 공주시 고마나루길 51-14",
                    "roadAddress": "충청남도 공주시 고마나루길 51-14",
                    "mapx": "1271110000",
                    "mapy": "364600000",
                }
            ]

    collector = PlaceCollector(
        kakao_client=FakeKakaoClient(),
        naver_client=FakeNaverClient(),
        output_root=tmp_path,
    )

    result = collector.collect(region_name="공주", queries=["공주 테스트"], tour_keywords=None)

    categories = {place.name: place.category for place in result.processed_places}
    assert categories["공주알밤한우 산성시장점"] == PlaceCategory.MARKET
    assert categories["로컬공방"] == PlaceCategory.CULTURE
    assert categories["백제체육관"] == PlaceCategory.ACTIVITY
    assert "공산성 매표소" not in categories


def test_place_collector_continues_when_naver_page_is_rate_limited(tmp_path) -> None:
    class FakeKakaoClient:
        def search_keyword(
            self,
            query: str,
            *,
            size: int = 15,
            page: int = 1,
        ) -> list[dict[str, object]]:
            if page > 1:
                return []
            return [
                {
                    "id": "kakao-1",
                    "place_name": "공산성",
                    "category_name": "여행 > 관광,명소 > 문화유적",
                    "category_group_code": "AT4",
                    "road_address_name": "충남 공주시 웅진로 280",
                    "address_name": "충남 공주시 금성동 53-51",
                    "x": "127.125997",
                    "y": "36.462293",
                    "phone": "",
                    "place_url": "https://place.map.kakao.com/1",
                }
            ]

    class FakeNaverClient:
        def search_local(
            self,
            query: str,
            *,
            display: int = 5,
            start: int = 1,
            sort: str = "random",
        ) -> list[dict[str, object]]:
            if start > 1:
                request = httpx.Request("GET", "https://openapi.naver.com/v1/search/local.json")
                response = httpx.Response(429, request=request)
                raise httpx.HTTPStatusError("rate limited", request=request, response=response)
            return [
                {
                    "title": "<b>공주산성시장</b>",
                    "link": "https://example.com/market",
                    "category": "쇼핑,유통>시장",
                    "description": "공주 대표 전통시장",
                    "address": "충남 공주시 산성동 120",
                    "roadAddress": "충남 공주시 용당길 22",
                    "mapx": "1271240000",
                    "mapy": "364620000",
                }
            ]

    class FakeTourClient:
        def search_keyword(
            self,
            keyword: str,
            *,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            if page > 1:
                return []
            return [
                {
                    "contentid": "tour-1",
                    "contenttypeid": "12",
                    "title": "공주 고마나루",
                    "addr1": "충남 공주시 백제큰길 2045",
                    "mapx": "127.106345",
                    "mapy": "36.468708",
                }
            ]

        def search_festivals(
            self,
            *,
            event_start_date: str,
            event_end_date: str | None = None,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return []

        def search_stays(
            self,
            *,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return []

    collector = PlaceCollector(
        kakao_client=FakeKakaoClient(),
        naver_client=FakeNaverClient(),
        tour_client=FakeTourClient(),
        output_root=tmp_path,
    )

    result = collector.collect(
        region_name="공주",
        queries=["공주 관광지"],
        tour_keywords=["공주"],
        kakao_pages=2,
        naver_pages=3,
        tour_pages=2,
    )

    names = {place.name for place in result.processed_places}
    assert {"공산성", "공주산성시장", "공주 고마나루"} <= names
    assert len(result.warnings) == 1
    assert result.warnings[0].startswith("NAVER_PAGE_FETCH_FAILED")


def test_place_collector_records_tour_api_warning_when_keyword_fetch_fails(tmp_path) -> None:
    class FakeKakaoClient:
        def search_keyword(
            self,
            query: str,
            *,
            size: int = 15,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return []

    class FakeNaverClient:
        def search_local(
            self,
            query: str,
            *,
            display: int = 5,
            start: int = 1,
            sort: str = "random",
        ) -> list[dict[str, object]]:
            return []

    class FakeTourClient:
        def search_keyword(
            self,
            keyword: str,
            *,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            request = httpx.Request("GET", "https://apis.data.go.kr/B551011/KorService2/searchKeyword2")
            response = httpx.Response(503, request=request)
            raise httpx.HTTPStatusError("service unavailable", request=request, response=response)

        def search_festivals(
            self,
            *,
            event_start_date: str,
            event_end_date: str | None = None,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return []

        def search_stays(
            self,
            *,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return []

    collector = PlaceCollector(
        kakao_client=FakeKakaoClient(),
        naver_client=FakeNaverClient(),
        tour_client=FakeTourClient(),
        output_root=tmp_path,
    )

    result = collector.collect(
        region_name="공주",
        queries=["공주 관광지"],
        tour_keywords=["공주"],
        tour_pages=2,
    )

    assert result.processed_places == []
    assert len(result.warnings) == 1
    assert result.warnings[0].startswith("TOUR_API_KEYWORD_FETCH_FAILED")


def test_place_collector_collects_sources_in_parallel(tmp_path) -> None:
    class SlowKakaoClient:
        def search_keyword(
            self,
            query: str,
            *,
            size: int = 15,
            page: int = 1,
        ) -> list[dict[str, object]]:
            time.sleep(0.2)
            return [
                {
                    "id": "kakao-1",
                    "place_name": "공산성",
                    "category_name": "여행 > 관광,명소 > 문화유적",
                    "category_group_code": "AT4",
                    "road_address_name": "충남 공주시 웅진로 280",
                    "address_name": "충남 공주시 금성동 53-51",
                    "x": "127.125997",
                    "y": "36.462293",
                    "phone": "",
                    "place_url": "https://place.map.kakao.com/1",
                }
            ]

    class SlowNaverClient:
        def search_local(
            self,
            query: str,
            *,
            display: int = 5,
            start: int = 1,
            sort: str = "random",
        ) -> list[dict[str, object]]:
            time.sleep(0.2)
            return [
                {
                    "title": "<b>루치아의뜰</b>",
                    "link": "https://example.com/place",
                    "category": "음식점>카페",
                    "description": "공주 한옥 카페",
                    "address": "충남 공주시 반죽동 100",
                    "roadAddress": "충남 공주시 웅진로 145",
                    "mapx": "1271234567",
                    "mapy": "361234567",
                }
            ]

    class SlowTourClient:
        def search_keyword(
            self,
            keyword: str,
            *,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            time.sleep(0.2)
            return [
                {
                    "contentid": "tour-1",
                    "contenttypeid": "12",
                    "title": "공주 고마나루",
                    "addr1": "충남 공주시 백제큰길 2045",
                    "mapx": "127.106345",
                    "mapy": "36.468708",
                }
            ]

        def search_festivals(
            self,
            *,
            event_start_date: str,
            event_end_date: str | None = None,
            area_code: int | None = None,
            sigungu_code: int | None = None,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return []

        def search_stays(
            self,
            *,
            rows: int = 20,
            page: int = 1,
        ) -> list[dict[str, object]]:
            return []

    collector = PlaceCollector(
        kakao_client=SlowKakaoClient(),
        naver_client=SlowNaverClient(),
        tour_client=SlowTourClient(),
        output_root=tmp_path,
    )

    started_at = time.perf_counter()
    result = collector.collect(
        region_name="공주",
        queries=["공주 관광지"],
        tour_keywords=["공주"],
    )
    elapsed = time.perf_counter() - started_at

    assert {place.name for place in result.processed_places} == {"공산성", "루치아의뜰", "공주 고마나루"}
    assert elapsed < 0.45
