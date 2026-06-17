from app.data.collection_queries import COMMON_QUERIES, FIRST_PHASE_REGIONS, build_queries


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


def test_common_queries_are_broad_enough_for_collection() -> None:
    assert len(COMMON_QUERIES) >= 40
    assert "{region}" in COMMON_QUERIES[0]
