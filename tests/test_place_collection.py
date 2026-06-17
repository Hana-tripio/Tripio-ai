import json

import httpx

from app.clients.kakao_local_client import KakaoLocalClient
from app.clients.naver_local_client import NaverLocalClient
from app.clients.tour_api_client import TourApiClient
from app.schemas.place_source import ExternalPlaceSource, NormalizedPlace, PlaceCategory
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
                "meta": {"total_count": 1},
            },
        )

    client = KakaoLocalClient(
        api_key="kakao-test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    results = client.search_keyword("공주 관광지", size=3)

    assert len(results) == 1
    assert results[0].place_name == "공산성"
    assert results[0].longitude == 127.125997
    assert results[0].latitude == 36.462293


def test_naver_local_client_searches_local_places() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/search/local.json"
        assert request.url.params["query"] == "공주 카페"
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

    results = client.search_local("공주 카페", display=3)

    assert len(results) == 1
    assert results[0].title == "루치아의뜰"
    assert results[0].longitude == 127.1234567
    assert results[0].latitude == 36.1234567


def test_tour_api_client_searches_keyword_places() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/B551011/KorService2/searchKeyword2"
        assert request.url.params["serviceKey"] == "tour-service-key"
        assert request.url.params["MobileOS"] == "ETC"
        assert request.url.params["MobileApp"] == "Tripio"
        assert request.url.params["_type"] == "json"
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

    results = client.search_keyword("공주", rows=5)

    assert len(results) == 1
    assert results[0].title == "공주 갑사 철당간"
    assert results[0].content_id == "126508"
    assert results[0].longitude == 127.1852806342
    assert results[0].latitude == 36.3646948037


def test_tour_api_client_searches_festivals_with_event_dates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/B551011/KorService2/searchFestival2"
        assert request.url.params["eventStartDate"] == "20260601"
        assert request.url.params["eventEndDate"] == "20260630"
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

    results = client.search_festivals(event_start_date="20260601", event_end_date="20260630")

    assert len(results) == 1
    assert results[0].title == "공주 문화유산 야행"
    assert results[0].event_start_date == "20260610"
    assert results[0].event_end_date == "20260612"


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
        def search_keyword(self, query: str, *, size: int = 15) -> list[dict[str, object]]:
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
        def search_keyword(self, keyword: str, *, rows: int = 20) -> list[dict[str, object]]:
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
