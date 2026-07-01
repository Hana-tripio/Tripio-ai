from pydantic import BaseModel

from app.schemas.place_source import NormalizedPlace, PlaceCategory, PlaceQualitySummary

RAW_CULTURE_KEYWORDS = ("문화시설", "문화원", "박물관", "미술관", "전시관")
RAW_MARKET_KEYWORDS = ("시장", "전통시장", "수산물", "농산물")
RAW_ACTIVITY_KEYWORDS = ("체험", "레저", "액티비티", "레일바이크", "케이블카")
RAW_ATTRACTION_KEYWORDS = ("관광", "명소", "유적", "사찰", "공원", "전망대", "폭포")
NAME_CULTURE_KEYWORDS = ("박물관", "미술관", "전시관")
NAME_MARKET_KEYWORDS = ("전통시장",)
NAME_ACTIVITY_KEYWORDS = ("레일바이크", "케이블카")
NAME_ATTRACTION_KEYWORDS: tuple[str, ...] = ()
PURE_SUPPORT_RAW_KEYWORDS = (
    "주차장",
    "전기차충전소",
    "충전소",
    "편의점",
    "교차로",
    "삼거리",
    "사거리",
    "출입구",
    "매표소",
    "매표",
    "ticket office",
    "ticket booth",
)
PURE_SUPPORT_NAME_KEYWORDS = (
    "주차장",
    "전기차충전소",
    "충전소",
    "교차로",
    "삼거리",
    "사거리",
    "출입구",
    "매표소",
)
TOUR_SUPPORT_RAW_KEYWORDS = ("관광지부속시설",)
TOUR_SUPPORT_FILTER_NAME_KEYWORDS = (
    "매점",
    "개수대",
    "화장실",
    "주차장",
    "관리사무소",
    "관리소",
    "안내소",
    "매표소",
    "쉼터",
    "숙박동",
    "개별숙박동",
    "취사장",
)
TOUR_SUPPORT_HUB_NAME_KEYWORDS = (
    "탐방지원센터",
    "방문자센터",
    "체험관",
    "전시관",
    "교육관",
)


class PlaceQualityResult(BaseModel):
    kept_places: list[NormalizedPlace]
    filtered_places: list[NormalizedPlace]
    summary: PlaceQualitySummary
    report: "PlaceQualityReport"


class PlaceQualityFilteredSample(BaseModel):
    name: str
    raw_category: str
    address: str


class PlaceQualityReclassifiedSample(BaseModel):
    name: str
    raw_category: str
    address: str
    from_category: PlaceCategory
    to_category: PlaceCategory


class PlaceQualityReport(BaseModel):
    summary: PlaceQualitySummary
    metadata: "PlaceQualityReportMetadata"
    filtered_samples: list[PlaceQualityFilteredSample]
    reclassified_samples: list[PlaceQualityReclassifiedSample]


class PlaceQualityReportMetadata(BaseModel):
    summary_input_count_basis: str
    summary_input_count_stage: str


def refine_place_quality(places: list[NormalizedPlace]) -> PlaceQualityResult:
    kept_places: list[NormalizedPlace] = []
    filtered_places: list[NormalizedPlace] = []
    reclassified_count = 0
    reclassified_samples: list[PlaceQualityReclassifiedSample] = []

    for place in places:
        if _should_filter(place):
            filtered_places.append(place)
            continue

        refined_place = place.model_copy(deep=True)
        if refined_place.category == PlaceCategory.ETC:
            refined_category = _reclassify_etc_place(refined_place)
            if refined_category != refined_place.category:
                previous_category = refined_place.category
                refined_place.category = refined_category
                reclassified_count += 1
                reclassified_samples.append(
                    PlaceQualityReclassifiedSample(
                        name=refined_place.name,
                        raw_category=refined_place.raw_category,
                        address=refined_place.address,
                        from_category=previous_category,
                        to_category=refined_category,
                    )
                )

        kept_places.append(refined_place)

    summary = PlaceQualitySummary(
        input_count=len(places),
        kept_count=len(kept_places),
        filtered_count=len(filtered_places),
        reclassified_count=reclassified_count,
    )

    return PlaceQualityResult(
        kept_places=kept_places,
        filtered_places=filtered_places,
        summary=summary,
        report=PlaceQualityReport(
            summary=summary,
            metadata=PlaceQualityReportMetadata(
                summary_input_count_basis=(
                    "Counts candidates after collector-side region filtering and collector "
                    "exclusions, before quality refinement filtering and reclassification."
                ),
                summary_input_count_stage=(
                    "post_region_filter_post_collector_exclusion_pre_quality_refinement"
                ),
            ),
            filtered_samples=[
                PlaceQualityFilteredSample(
                    name=place.name,
                    raw_category=place.raw_category,
                    address=place.address,
                )
                for place in filtered_places[:20]
            ],
            reclassified_samples=reclassified_samples[:20],
        ),
    )


def _should_filter(place: NormalizedPlace) -> bool:
    if place.category != PlaceCategory.ETC:
        return False

    name_text = _normalized_text(place.name)
    raw_category_text = _normalized_text(place.raw_category)

    if _contains_any(raw_category_text, PURE_SUPPORT_RAW_KEYWORDS):
        return True
    if _is_filtered_tour_support_facility(name_text, raw_category_text):
        return True

    return _contains_any(name_text, PURE_SUPPORT_NAME_KEYWORDS)


def _reclassify_etc_place(place: NormalizedPlace) -> PlaceCategory:
    name_text = _normalized_text(place.name)
    raw_category_text = _normalized_text(place.raw_category)

    if _is_tour_support_hub(name_text, raw_category_text):
        return PlaceCategory.ACTIVITY

    if _contains_any(raw_category_text, RAW_CULTURE_KEYWORDS) or _contains_any(
        name_text,
        NAME_CULTURE_KEYWORDS,
    ):
        return PlaceCategory.CULTURE
    if _contains_any(raw_category_text, RAW_MARKET_KEYWORDS) or _contains_any(
        name_text,
        NAME_MARKET_KEYWORDS,
    ):
        return PlaceCategory.MARKET
    if _contains_any(raw_category_text, RAW_ACTIVITY_KEYWORDS) or _contains_any(
        name_text,
        NAME_ACTIVITY_KEYWORDS,
    ):
        return PlaceCategory.ACTIVITY
    if _contains_any(raw_category_text, RAW_ATTRACTION_KEYWORDS) or _contains_any(
        name_text,
        NAME_ATTRACTION_KEYWORDS,
    ):
        return PlaceCategory.TOURIST_ATTRACTION
    return place.category


def _normalized_text(*values: str) -> str:
    return " ".join(value.strip().lower() for value in values if value)


def _contains_any(value: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in value for keyword in keywords)


def _is_filtered_tour_support_facility(name_text: str, raw_category_text: str) -> bool:
    return _contains_any(raw_category_text, TOUR_SUPPORT_RAW_KEYWORDS) and _contains_any(
        name_text,
        TOUR_SUPPORT_FILTER_NAME_KEYWORDS,
    )


def _is_tour_support_hub(name_text: str, raw_category_text: str) -> bool:
    return _contains_any(raw_category_text, TOUR_SUPPORT_RAW_KEYWORDS) and _contains_any(
        name_text,
        TOUR_SUPPORT_HUB_NAME_KEYWORDS,
    )
