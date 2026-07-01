from app.schemas.place_source import ExternalPlaceSource, NormalizedPlace, PlaceCategory
from app.services.place_quality import refine_place_quality


def _place(
    *,
    source_place_id: str,
    name: str,
    category: PlaceCategory,
    raw_category: str = "",
) -> NormalizedPlace:
    return NormalizedPlace(
        source=ExternalPlaceSource.KAKAO,
        source_place_id=source_place_id,
        name=name,
        region_name="공주",
        address="충남 공주시",
        road_address="충남 공주시",
        latitude=36.5,
        longitude=127.1,
        category=category,
        source_query="공주 여행",
        raw_category=raw_category,
    )


def test_refine_place_quality_reclassifies_supported_etc_places() -> None:
    places = [
        _place(
            source_place_id="etc-culture",
            name="공주박물관",
            category=PlaceCategory.ETC,
            raw_category="문화시설 > 박물관",
        ),
        _place(
            source_place_id="etc-market",
            name="산성시장",
            category=PlaceCategory.ETC,
            raw_category="시장",
        ),
        _place(
            source_place_id="etc-activity",
            name="공주레일바이크",
            category=PlaceCategory.ETC,
            raw_category="레저,체험",
        ),
        _place(
            source_place_id="etc-attraction",
            name="공산성",
            category=PlaceCategory.ETC,
            raw_category="관광,명소 > 문화유적",
        ),
    ]

    result = refine_place_quality(places)

    assert [place.category for place in result.kept_places] == [
        PlaceCategory.CULTURE,
        PlaceCategory.MARKET,
        PlaceCategory.ACTIVITY,
        PlaceCategory.TOURIST_ATTRACTION,
    ]
    assert result.filtered_places == []
    assert result.summary.input_count == 4
    assert result.summary.kept_count == 4
    assert result.summary.filtered_count == 0
    assert result.summary.reclassified_count == 4


def test_refine_place_quality_filters_non_trip_support_places() -> None:
    places = [
        _place(
            source_place_id="parking",
            name="공산성 주차장",
            category=PlaceCategory.ETC,
            raw_category="주차장",
        ),
        _place(
            source_place_id="ev",
            name="급속 전기차충전소",
            category=PlaceCategory.ETC,
            raw_category="전기차충전소",
        ),
        _place(
            source_place_id="store",
            name="공산성점 CU",
            category=PlaceCategory.ETC,
            raw_category="편의점",
        ),
        _place(
            source_place_id="intersection",
            name="산성입구삼거리",
            category=PlaceCategory.ETC,
            raw_category="교차로",
        ),
        _place(
            source_place_id="entrance",
            name="무령왕릉 입구",
            category=PlaceCategory.ETC,
            raw_category="출입구",
        ),
        _place(
            source_place_id="ticket",
            name="매표소",
            category=PlaceCategory.ETC,
            raw_category="매표소",
        ),
    ]

    result = refine_place_quality(places)

    assert result.kept_places == []
    assert [place.source_place_id for place in result.filtered_places] == [
        "parking",
        "ev",
        "store",
        "intersection",
        "entrance",
        "ticket",
    ]
    assert result.summary.input_count == 6
    assert result.summary.kept_count == 0
    assert result.summary.filtered_count == 6
    assert result.summary.reclassified_count == 0


def test_refine_place_quality_keeps_non_etc_categories_as_is() -> None:
    places = [
        _place(
            source_place_id="restaurant",
            name="맛집식당",
            category=PlaceCategory.RESTAURANT,
            raw_category="문화시설 > 박물관",
        ),
        _place(
            source_place_id="culture",
            name="기존문화공간",
            category=PlaceCategory.CULTURE,
            raw_category="시장",
        ),
    ]

    result = refine_place_quality(places)

    assert [place.category for place in result.kept_places] == [
        PlaceCategory.RESTAURANT,
        PlaceCategory.CULTURE,
    ]
    assert result.filtered_places == []
    assert result.summary.input_count == 2
    assert result.summary.kept_count == 2
    assert result.summary.filtered_count == 0
    assert result.summary.reclassified_count == 0


def test_refine_place_quality_keeps_non_etc_places_with_filter_like_text() -> None:
    places = [
        _place(
            source_place_id="tourist-entrance",
            name="공산성 입구",
            category=PlaceCategory.TOURIST_ATTRACTION,
            raw_category="매표소 안내",
        )
    ]

    result = refine_place_quality(places)

    assert [place.source_place_id for place in result.kept_places] == ["tourist-entrance"]
    assert [place.category for place in result.kept_places] == [PlaceCategory.TOURIST_ATTRACTION]
    assert result.filtered_places == []
    assert result.summary.input_count == 1
    assert result.summary.kept_count == 1
    assert result.summary.filtered_count == 0
    assert result.summary.reclassified_count == 0


def test_refine_place_quality_does_not_treat_every_seong_as_attraction() -> None:
    places = [
        _place(
            source_place_id="samsung-store",
            name="삼성스토어 공주점",
            category=PlaceCategory.ETC,
            raw_category="전자제품판매",
        )
    ]

    result = refine_place_quality(places)

    assert [place.category for place in result.kept_places] == [PlaceCategory.ETC]
    assert result.filtered_places == []
    assert result.summary.input_count == 1
    assert result.summary.kept_count == 1
    assert result.summary.filtered_count == 0
    assert result.summary.reclassified_count == 0


def test_refine_place_quality_keeps_legitimate_etc_destinations_with_entrance_like_text() -> None:
    places = [
        _place(
            source_place_id="entrance-garden",
            name="달빛정원 입구광장",
            category=PlaceCategory.ETC,
            raw_category="공원",
        ),
        _place(
            source_place_id="ticket-museum",
            name="티켓뮤지엄",
            category=PlaceCategory.ETC,
            raw_category="박물관",
        ),
    ]

    result = refine_place_quality(places)

    assert [place.source_place_id for place in result.kept_places] == [
        "entrance-garden",
        "ticket-museum",
    ]
    assert [place.category for place in result.kept_places] == [
        PlaceCategory.TOURIST_ATTRACTION,
        PlaceCategory.CULTURE,
    ]
    assert result.filtered_places == []
    assert result.summary.input_count == 2
    assert result.summary.kept_count == 2
    assert result.summary.filtered_count == 0
    assert result.summary.reclassified_count == 2


def test_refine_place_quality_does_not_reclassify_generic_market_word_in_name() -> None:
    places = [
        _place(
            source_place_id="market-pharmacy",
            name="시장약국",
            category=PlaceCategory.ETC,
            raw_category="약국",
        )
    ]

    result = refine_place_quality(places)

    assert [place.category for place in result.kept_places] == [PlaceCategory.ETC]
    assert result.filtered_places == []
    assert result.summary.input_count == 1
    assert result.summary.kept_count == 1
    assert result.summary.filtered_count == 0
    assert result.summary.reclassified_count == 0


def test_refine_place_quality_does_not_reclassify_generic_attraction_words_in_name() -> None:
    places = [
        _place(
            source_place_id="park-laundry",
            name="공원세탁소",
            category=PlaceCategory.ETC,
            raw_category="세탁소",
        ),
        _place(
            source_place_id="waterfall-karaoke",
            name="폭포노래연습장",
            category=PlaceCategory.ETC,
            raw_category="노래방",
        ),
    ]

    result = refine_place_quality(places)

    assert [place.source_place_id for place in result.kept_places] == [
        "park-laundry",
        "waterfall-karaoke",
    ]
    assert [place.category for place in result.kept_places] == [
        PlaceCategory.ETC,
        PlaceCategory.ETC,
    ]
    assert result.filtered_places == []
    assert result.summary.input_count == 2
    assert result.summary.kept_count == 2
    assert result.summary.filtered_count == 0
    assert result.summary.reclassified_count == 0


def test_refine_place_quality_filters_mixed_destination_support_raw_categories() -> None:
    places = [
        _place(
            source_place_id="museum-ticket",
            name="공주역사박물관 안내",
            category=PlaceCategory.ETC,
            raw_category="문화시설 > 박물관 > 매표소",
        ),
        _place(
            source_place_id="park-gate",
            name="달빛공원 동문",
            category=PlaceCategory.ETC,
            raw_category="관광 > 공원 출입구",
        ),
    ]

    result = refine_place_quality(places)

    assert result.kept_places == []
    assert [place.source_place_id for place in result.filtered_places] == [
        "museum-ticket",
        "park-gate",
    ]
    assert result.summary.input_count == 2
    assert result.summary.kept_count == 0
    assert result.summary.filtered_count == 2
    assert result.summary.reclassified_count == 0


def test_refine_place_quality_does_not_auto_promote_broad_commerce_raw_categories() -> None:
    places = [
        _place(
            source_place_id="bookstore",
            name="동네책방",
            category=PlaceCategory.ETC,
            raw_category="서점",
        ),
        _place(
            source_place_id="souvenir-shop",
            name="고향선물가게",
            category=PlaceCategory.ETC,
            raw_category="특산물",
        ),
        _place(
            source_place_id="craft-shop",
            name="생활목공소",
            category=PlaceCategory.ETC,
            raw_category="공방",
        ),
    ]

    result = refine_place_quality(places)

    assert [place.source_place_id for place in result.kept_places] == [
        "bookstore",
        "souvenir-shop",
        "craft-shop",
    ]
    assert [place.category for place in result.kept_places] == [
        PlaceCategory.ETC,
        PlaceCategory.ETC,
        PlaceCategory.ETC,
    ]
    assert result.filtered_places == []
    assert result.summary.input_count == 3
    assert result.summary.kept_count == 3
    assert result.summary.filtered_count == 0
    assert result.summary.reclassified_count == 0


def test_refine_place_quality_filters_destination_infrastructure_mixed_raw_categories() -> None:
    places = [
        _place(
            source_place_id="park-parking",
            name="달빛공원 주차장",
            category=PlaceCategory.ETC,
            raw_category="관광 > 공원 주차장",
        ),
        _place(
            source_place_id="museum-parking",
            name="역사박물관 주차장",
            category=PlaceCategory.ETC,
            raw_category="문화시설 > 박물관 주차장",
        ),
        _place(
            source_place_id="market-ev",
            name="산성시장 전기차충전소",
            category=PlaceCategory.ETC,
            raw_category="전통시장 충전소",
        ),
    ]

    result = refine_place_quality(places)

    assert result.kept_places == []
    assert [place.source_place_id for place in result.filtered_places] == [
        "park-parking",
        "museum-parking",
        "market-ev",
    ]
    assert result.summary.input_count == 3
    assert result.summary.kept_count == 0
    assert result.summary.filtered_count == 3
    assert result.summary.reclassified_count == 0


def test_refine_place_quality_does_not_promote_name_only_sanseong_or_eupseong() -> None:
    places = [
        _place(
            source_place_id="sanseong-cafe",
            name="산성카페",
            category=PlaceCategory.ETC,
            raw_category="카페거리",
        ),
        _place(
            source_place_id="eupseong-shop",
            name="읍성상회",
            category=PlaceCategory.ETC,
            raw_category="잡화점",
        ),
    ]

    result = refine_place_quality(places)

    assert [place.source_place_id for place in result.kept_places] == [
        "sanseong-cafe",
        "eupseong-shop",
    ]
    assert [place.category for place in result.kept_places] == [
        PlaceCategory.ETC,
        PlaceCategory.ETC,
    ]
    assert result.filtered_places == []
    assert result.summary.input_count == 2
    assert result.summary.kept_count == 2
    assert result.summary.filtered_count == 0
    assert result.summary.reclassified_count == 0


def test_refine_place_quality_filters_tour_support_facilities() -> None:
    places = [
        _place(
            source_place_id="tour-shop",
            name="동학사야영장 매점",
            category=PlaceCategory.ETC,
            raw_category="여행 > 관광지부속시설",
        ),
        _place(
            source_place_id="tour-sink",
            name="동학사야영장 개수대",
            category=PlaceCategory.ETC,
            raw_category="여행 > 관광지부속시설",
        ),
        _place(
            source_place_id="tour-room",
            name="공주한옥마을 개별숙박동",
            category=PlaceCategory.ETC,
            raw_category="여행 > 관광지부속시설",
        ),
    ]

    result = refine_place_quality(places)

    assert result.kept_places == []
    assert [place.source_place_id for place in result.filtered_places] == [
        "tour-shop",
        "tour-sink",
        "tour-room",
    ]
    assert result.summary.input_count == 3
    assert result.summary.kept_count == 0
    assert result.summary.filtered_count == 3
    assert result.summary.reclassified_count == 0


def test_refine_place_quality_keeps_and_reclassifies_tour_support_hubs() -> None:
    places = [
        _place(
            source_place_id="tour-hub",
            name="계룡산 동학사탐방지원센터",
            category=PlaceCategory.ETC,
            raw_category="여행 > 관광지부속시설",
        )
    ]

    result = refine_place_quality(places)

    assert [place.source_place_id for place in result.kept_places] == ["tour-hub"]
    assert [place.category for place in result.kept_places] == [PlaceCategory.ACTIVITY]
    assert result.filtered_places == []
    assert result.summary.input_count == 1
    assert result.summary.kept_count == 1
    assert result.summary.filtered_count == 0
    assert result.summary.reclassified_count == 1
