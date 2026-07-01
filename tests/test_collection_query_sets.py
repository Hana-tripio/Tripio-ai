from app.data.collection_queries import (
    COMMON_QUERIES,
    FIRST_PHASE_REGIONS,
    SECOND_PHASE_REGIONS,
    THIRD_PHASE_REGIONS,
    SUPPORTED_QUERY_REGIONS,
    build_queries,
)


def test_build_queries_includes_common_and_region_specific_queries() -> None:
    queries = build_queries("공주")

    assert "공주 맛집" in queries
    assert "공주 1박2일 여행" in queries
    assert "공주 역사 여행" in queries
    assert "공주 백제 여행" in queries


def test_build_queries_deduplicates_overlapping_queries() -> None:
    queries = build_queries("공주")

    assert queries.count("공주 역사 여행") == 1
    assert len(queries) == len(set(queries))


def test_first_phase_regions_have_query_sets() -> None:
    for region_name in FIRST_PHASE_REGIONS:
        queries = build_queries(region_name)
        assert queries
        assert all(region_name in query for query in queries)


def test_second_phase_regions_have_query_sets() -> None:
    for region_name in SECOND_PHASE_REGIONS:
        queries = build_queries(region_name)
        assert queries
        assert all(region_name in query for query in queries)


def test_supported_query_regions_combine_first_and_second_phase() -> None:
    assert set(SUPPORTED_QUERY_REGIONS) == (
        set(FIRST_PHASE_REGIONS) | set(SECOND_PHASE_REGIONS) | set(THIRD_PHASE_REGIONS)
    )


def test_common_queries_are_broad_enough_for_collection() -> None:
    assert len(COMMON_QUERIES) >= 40
    assert "{region}" in COMMON_QUERIES[0]


def test_second_phase_low_coverage_regions_include_landmark_queries() -> None:
    goesan_queries = build_queries("괴산")
    yesan_queries = build_queries("예산")
    nonsan_queries = build_queries("논산")

    assert "괴산 쌍곡계곡" in goesan_queries
    assert "괴산 산막이옛길" in goesan_queries
    assert "괴산 화양구곡" in goesan_queries

    assert "예산 예당관광지" in yesan_queries
    assert "예산 내포보부상촌" in yesan_queries
    assert "예산 시장 투어" in yesan_queries

    assert "논산 강경 여행" in nonsan_queries
    assert "논산 선샤인랜드" in nonsan_queries
    assert "논산 연산문화창고" in nonsan_queries


def test_third_phase_regions_have_query_sets() -> None:
    for region_name in THIRD_PHASE_REGIONS:
        queries = build_queries(region_name)
        assert queries
        assert all(region_name in query for query in queries)


def test_third_phase_regions_include_landmark_queries() -> None:
    assert "태안 꽃지해수욕장" in build_queries("태안")
    assert "서천 국립생태원" in build_queries("서천")
    assert "당진 삽교호" in build_queries("당진")
    assert "홍성 남당항" in build_queries("홍성")
    assert "금산 인삼시장" in build_queries("금산")
    assert "계룡 신도안" in build_queries("계룡")
    assert "청양 알프스마을" in build_queries("청양")
    assert "보은 속리산" in build_queries("보은")
    assert "옥천 대청호" in build_queries("옥천")
    assert "영동 와인터널" in build_queries("영동")
    assert "음성 반기문평화기념관" in build_queries("음성")
    assert "진천 농다리" in build_queries("진천")
    assert "증평 좌구산" in build_queries("증평")
