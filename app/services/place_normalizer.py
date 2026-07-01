import re
from collections.abc import Mapping
from typing import Any

from app.clients.kakao_local_client import KakaoKeywordPlace
from app.clients.naver_local_client import NaverLocalPlace
from app.clients.tour_api_client import TourApiPlace
from app.schemas.place_source import ExternalPlaceSource, NormalizedPlace, PlaceCategory

TAG_PATTERN = re.compile(r"<[^>]+>")


def normalize_kakao_place(
    raw_place: KakaoKeywordPlace | Mapping[str, Any],
    *,
    region_name: str,
    query: str,
) -> NormalizedPlace:
    data = _to_mapping(raw_place)
    category_name = str(data.get("category_name", ""))
    category_group_code = str(data.get("category_group_code", ""))
    road_address = str(data.get("road_address_name", ""))
    address = road_address or str(data.get("address_name", ""))
    category = _map_kakao_category(category_group_code, category_name)

    return NormalizedPlace(
        source=ExternalPlaceSource.KAKAO,
        source_place_id=str(data.get("id", "")),
        name=str(data.get("place_name", "")).strip(),
        region_name=region_name,
        address=address,
        road_address=road_address,
        latitude=float(data.get("y", 0.0)),
        longitude=float(data.get("x", 0.0)),
        category=category,
        source_query=query,
        raw_category=category_name,
        phone=str(data.get("phone", "")),
        url=str(data.get("place_url", "")),
        tags=_with_primary_tag(category, _extract_tags(category_name)),
    )


def normalize_naver_place(
    raw_place: NaverLocalPlace | Mapping[str, Any],
    *,
    region_name: str,
    query: str,
) -> NormalizedPlace:
    data = _to_mapping(raw_place)
    category_name = str(data.get("category", ""))
    road_address = str(data.get("roadAddress", ""))
    address = road_address or str(data.get("address", ""))
    category = _map_naver_category(category_name)

    return NormalizedPlace(
        source=ExternalPlaceSource.NAVER,
        source_place_id=str(data.get("link", "")) or _clean_html(str(data.get("title", ""))),
        name=_clean_html(str(data.get("title", ""))).strip(),
        region_name=region_name,
        address=address,
        road_address=road_address,
        latitude=int(str(data.get("mapy", "0"))) / 10_000_000,
        longitude=int(str(data.get("mapx", "0"))) / 10_000_000,
        category=category,
        source_query=query,
        raw_category=category_name,
        url=str(data.get("link", "")),
        description=_clean_html(str(data.get("description", ""))),
        tags=_with_primary_tag(category, _extract_tags(category_name)),
    )


def normalize_tour_place(
    raw_place: TourApiPlace | Mapping[str, Any],
    *,
    region_name: str,
    query: str,
) -> NormalizedPlace:
    data = _to_mapping(raw_place)
    content_type_id = str(data.get("contenttypeid") or data.get("content_type_id", ""))
    category = _map_tour_content_type(content_type_id)
    tags = _tour_tags(category, data)

    return NormalizedPlace(
        source=ExternalPlaceSource.TOUR_API,
        source_place_id=str(data.get("contentid") or data.get("content_id", "")),
        name=str(data.get("title", "")).strip(),
        region_name=region_name,
        address=str(data.get("addr1") or data.get("address", "")),
        road_address=str(data.get("addr1") or data.get("address", "")),
        latitude=float(data.get("mapy") or data.get("map_y") or 0.0),
        longitude=float(data.get("mapx") or data.get("map_x") or 0.0),
        category=category,
        source_query=query,
        raw_category=content_type_id,
        phone=str(data.get("tel", "")),
        image_url=str(data.get("firstimage") or data.get("image_url", "")),
        tags=tags,
    )


def _to_mapping(
    value: KakaoKeywordPlace | NaverLocalPlace | TourApiPlace | Mapping[str, Any],
) -> Mapping[str, Any]:
    if isinstance(value, KakaoKeywordPlace | NaverLocalPlace | TourApiPlace):
        return value.model_dump(by_alias=True)
    return value


def _clean_html(value: str) -> str:
    return TAG_PATTERN.sub("", value)


def _extract_tags(category_name: str) -> list[str]:
    raw_parts = re.split(r"[>\\/]", category_name)
    tags = [part.strip() for part in raw_parts if part.strip()]
    return [tag for tag in tags if tag not in {"여행", "관광,명소", "음식점", "쇼핑,유통"}]


def _with_primary_tag(category: PlaceCategory, tags: list[str]) -> list[str]:
    primary_tags = {
        PlaceCategory.TOURIST_ATTRACTION: "관광지",
        PlaceCategory.RESTAURANT: "식당",
        PlaceCategory.CAFE: "카페",
        PlaceCategory.LODGING: "숙소",
        PlaceCategory.MARKET: "시장",
    }
    primary = primary_tags.get(category)
    if primary and primary not in tags:
        return [primary, *tags]
    return tags


def _tour_tags(category: PlaceCategory, data: Mapping[str, Any]) -> list[str]:
    if category == PlaceCategory.ACTIVITY and str(
        data.get("eventstartdate") or data.get("event_start_date", "")
    ):
        return ["체험/액티비티", "축제"]
    if category == PlaceCategory.CULTURE:
        return ["문화시설"]
    return _with_primary_tag(category, [])


def _map_kakao_category(category_group_code: str, category_name: str) -> PlaceCategory:
    if category_group_code == "FD6":
        return PlaceCategory.RESTAURANT
    if category_group_code == "CE7":
        return PlaceCategory.CAFE
    if category_group_code == "AD5":
        return PlaceCategory.LODGING
    if category_group_code == "AT4":
        if "시장" in category_name:
            return PlaceCategory.MARKET
        if "문화" in category_name or "유적" in category_name:
            return PlaceCategory.TOURIST_ATTRACTION
        return PlaceCategory.TOURIST_ATTRACTION
    if "시장" in category_name:
        return PlaceCategory.MARKET
    if (
        "특산물" in category_name
        or "관광민예품" in category_name
        or "전통식품" in category_name
        or "기념품판매" in category_name
        or "식품판매" in category_name
        or "정육점" in category_name
        or "과일,채소가게" in category_name
        or "수산물판매" in category_name
    ):
        return PlaceCategory.MARKET
    if "공원" in category_name or "절,사찰" in category_name:
        return PlaceCategory.TOURIST_ATTRACTION
    if "템플스테이" in category_name:
        return PlaceCategory.LODGING
    if "관광,명소" in category_name or "문화유적" in category_name:
        return PlaceCategory.TOURIST_ATTRACTION
    if (
        "문화시설" in category_name
        or "문화원" in category_name
        or "도서관" in category_name
        or "문화센터" in category_name
        or "문화의집" in category_name
        or "청소년문화센터" in category_name
        or "공방" in category_name
        or "미술,공예" in category_name
        or "목공예" in category_name
        or "독립서점" in category_name
        or "사진관,포토스튜디오" in category_name
        or "셀프,대여스튜디오" in category_name
        or "도서" in category_name
    ):
        return PlaceCategory.CULTURE
    if (
        "체험여행" in category_name
        or "체험학습장" in category_name
        or "체험마을" in category_name
        or "체험농장" in category_name
        or "주말농장" in category_name
        or "휴양마을" in category_name
        or "청소년수련시설" in category_name
        or "놀이터" in category_name
        or "실내체육관" in category_name
        or "오락실" in category_name
        or "골프연습장" in category_name
        or "파3골프장" in category_name
    ):
        return PlaceCategory.ACTIVITY
    if "카페" in category_name:
        return PlaceCategory.CAFE
    if (
        "음식점" in category_name
        or "중식" in category_name
        or "일식" in category_name
        or "양식" in category_name
        or "분식" in category_name
        or "치킨" in category_name
        or "국밥" in category_name
        or "칼국수" in category_name
        or "냉면" in category_name
        or "한정식" in category_name
        or "고기" in category_name
        or "포장마차" in category_name
    ):
        return PlaceCategory.RESTAURANT
    if "숙박" in category_name:
        return PlaceCategory.LODGING
    return PlaceCategory.ETC


def _map_naver_category(category_name: str) -> PlaceCategory:
    if "카페" in category_name:
        return PlaceCategory.CAFE
    if (
        "음식점" in category_name
        or "한식" in category_name
        or "맛집" in category_name
        or "중식" in category_name
        or "중식당" in category_name
        or "일식" in category_name
        or "양식" in category_name
        or "분식" in category_name
        or "치킨" in category_name
    ):
        return PlaceCategory.RESTAURANT
    if "숙박" in category_name or "호텔" in category_name or "펜션" in category_name:
        return PlaceCategory.LODGING
    if "시장" in category_name:
        return PlaceCategory.MARKET
    if (
        "특산물" in category_name
        or "관광민예품" in category_name
        or "전통식품" in category_name
        or "기념품판매" in category_name
        or "식품판매" in category_name
        or "정육점" in category_name
        or "과일,채소가게" in category_name
        or "수산물판매" in category_name
        or "유기농산물" in category_name
    ):
        return PlaceCategory.MARKET
    if (
        "문화시설" in category_name
        or "문화원" in category_name
        or "도서관" in category_name
        or "문화센터" in category_name
        or "문화의집" in category_name
        or "청소년문화센터" in category_name
        or "공방" in category_name
        or "미술,공예" in category_name
        or "목공예" in category_name
        or "독립서점" in category_name
        or "사진관,포토스튜디오" in category_name
        or "셀프,대여스튜디오" in category_name
        or "도서" in category_name
    ):
        return PlaceCategory.CULTURE
    if "템플스테이" in category_name:
        return PlaceCategory.LODGING
    if "공원" in category_name or "절,사찰" in category_name:
        return PlaceCategory.TOURIST_ATTRACTION
    if "문화" in category_name or "유적" in category_name or "명소" in category_name:
        return PlaceCategory.TOURIST_ATTRACTION
    if (
        "관람,체험" in category_name
        or "체험" in category_name
        or "체험마을" in category_name
        or "주말농장" in category_name
        or "휴양마을" in category_name
        or "실내체육관" in category_name
        or "오락실" in category_name
        or "골프연습장" in category_name
        or "파3골프장" in category_name
    ):
        return PlaceCategory.ACTIVITY
    if "포장마차" in category_name:
        return PlaceCategory.RESTAURANT
    return PlaceCategory.ETC


def _map_tour_content_type(content_type_id: str) -> PlaceCategory:
    if content_type_id == "12":
        return PlaceCategory.TOURIST_ATTRACTION
    if content_type_id == "14":
        return PlaceCategory.CULTURE
    if content_type_id == "15":
        return PlaceCategory.ACTIVITY
    if content_type_id == "28":
        return PlaceCategory.ACTIVITY
    if content_type_id == "32":
        return PlaceCategory.LODGING
    if content_type_id == "38":
        return PlaceCategory.MARKET
    if content_type_id == "39":
        return PlaceCategory.RESTAURANT
    return PlaceCategory.ETC
