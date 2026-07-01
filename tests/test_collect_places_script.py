import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.collection_config import (
    CollectionRunConfig,
    CollectionSourcesConfig,
    TourApiCollectionConfig,
    load_collection_run_config,
)
from app.schemas.place_source import (
    ExternalPlaceSource,
    NormalizedPlace,
    PlaceCategory,
    PlaceCollectionResult,
    PlaceQualitySummary,
)
from app.services.place_collector import PlaceCollector
from scripts.collect_places import (
    _print_collection_summary,
    _resolve_run_config,
    _resolve_tour_keywords,
)


def test_print_collection_summary_outputs_warnings(capsys) -> None:
    result = PlaceCollectionResult(
        region_name="공주",
        queries=["공주 관광지"],
        processed_places=[
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
            )
        ],
        quality_summary=PlaceQualitySummary(
            input_count=3,
            kept_count=1,
            filtered_count=2,
            reclassified_count=1,
        ),
        warnings=[
            "TOUR_API_KEYWORD_FETCH_FAILED keyword=공주 page=1 status=503",
            "NAVER_PAGE_FETCH_FAILED query=공주 관광지 start=6 status=429",
        ],
    )

    _print_collection_summary(result, "/tmp/tripio-data")

    captured = capsys.readouterr()
    assert "region=공주" in captured.out
    assert "processed_places=1" in captured.out
    assert "quality_input=3" in captured.out
    assert "quality_kept=1" in captured.out
    assert "quality_filtered=2" in captured.out
    assert "quality_reclassified=1" in captured.out
    assert "warnings_count=2" in captured.out
    assert "warning=TOUR_API_KEYWORD_FETCH_FAILED keyword=공주 page=1 status=503" in captured.out
    assert "warning=NAVER_PAGE_FETCH_FAILED query=공주 관광지 start=6 status=429" in captured.out


def test_place_collector_writes_quality_report_json(tmp_path: Path) -> None:
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
                    "id": "kakao-intersection",
                    "place_name": "유구전통시장 삼거리",
                    "category_name": "교통,수송 > 도로시설 > 삼거리",
                    "category_group_code": "",
                    "road_address_name": "충남 공주시 유구읍 석남리 275-11",
                    "address_name": "충남 공주시 유구읍 석남리 275-11",
                    "x": "126.951000",
                    "y": "36.553000",
                    "phone": "",
                    "place_url": "https://place.map.kakao.com/intersection",
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
                }
            ]

    collector = PlaceCollector(
        kakao_client=FakeKakaoClient(),
        naver_client=FakeNaverClient(),
        output_root=tmp_path,
    )

    result = collector.collect(region_name="공주", queries=["공주 문화"], tour_keywords=None)

    report_path = tmp_path / "processed" / "reports" / "gongju_quality_report.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert result.quality_summary.input_count == 3
    assert result.quality_summary.kept_count == 2
    assert result.quality_summary.filtered_count == 1
    assert result.quality_summary.reclassified_count == 1
    assert payload["summary"] == {
        "input_count": 3,
        "kept_count": 2,
        "filtered_count": 1,
        "reclassified_count": 1,
    }
    assert payload["metadata"] == {
        "summary_input_count_basis": (
            "Counts candidates after collector-side region filtering and collector exclusions, "
            "before quality refinement filtering and reclassification."
        ),
        "summary_input_count_stage": (
            "post_region_filter_post_collector_exclusion_pre_quality_refinement"
        ),
    }
    assert payload["filtered_samples"] == [
        {
            "name": "유구전통시장 삼거리",
            "raw_category": "교통,수송 > 도로시설 > 삼거리",
            "address": "충남 공주시 유구읍 석남리 275-11",
        }
    ]
    assert payload["reclassified_samples"] == [
        {
            "name": "공주역사박물관",
            "raw_category": "문화,예술 > 박물관",
            "address": "충남 공주시 번영1로 97-12",
            "from_category": "ETC",
            "to_category": "CULTURE",
        }
    ]


def test_load_collection_run_config_merges_base_and_region_yaml(tmp_path: Path) -> None:
    config_root = tmp_path / "configs" / "collection"
    regions_root = config_root / "regions"
    regions_root.mkdir(parents=True)

    (config_root / "base.yaml").write_text(
        "\n".join(
            [
                "output_root: data",
                "save_db: false",
                "province: 충청남도",
                "sources:",
                "  kakao:",
                "    enabled: true",
                "    pages: 5",
                "    concurrency: 2",
                "  naver:",
                "    enabled: true",
                "    pages: 2",
                "    concurrency: 1",
                "  tour_api:",
                "    enabled: true",
                "    pages: 3",
                "    rows: 40",
                "    festivals: false",
                "    stays: false",
                "    concurrency: 2",
            ]
        ),
        encoding="utf-8",
    )
    region_config = regions_root / "gongju.yaml"
    region_config.write_text(
        "\n".join(
            [
                "region: 공주",
                "save_db: true",
                "queries:",
                "  - 공주 관광지",
                "  - 공주 카페",
                "sources:",
                "  kakao:",
                "    pages: 7",
                "  tour_api:",
                "    festivals: true",
                "festival:",
                "  start_date: 20260101",
                "  end_date: 20261231",
            ]
        ),
        encoding="utf-8",
    )

    config = load_collection_run_config(region_config)

    assert config.region == "공주"
    assert config.save_db is True
    assert config.output_root == "data"
    assert config.queries == ["공주 관광지", "공주 카페"]
    assert config.sources.kakao.pages == 7
    assert config.sources.kakao.concurrency == 2
    assert config.sources.naver.pages == 2
    assert config.sources.tour_api.pages == 3
    assert config.sources.tour_api.rows == 40
    assert config.sources.tour_api.festivals is True
    assert config.festival_start_date == "20260101"
    assert config.festival_end_date == "20261231"


def test_resolve_run_config_prefers_cli_over_yaml(tmp_path: Path) -> None:
    config_root = tmp_path / "configs" / "collection"
    regions_root = config_root / "regions"
    regions_root.mkdir(parents=True)

    (config_root / "base.yaml").write_text(
        "\n".join(
            [
                "output_root: data",
                "save_db: false",
                "province: 충청남도",
                "sources:",
                "  kakao:",
                "    enabled: true",
                "    pages: 5",
                "    concurrency: 2",
                "  naver:",
                "    enabled: true",
                "    pages: 2",
                "    concurrency: 1",
                "  tour_api:",
                "    enabled: true",
                "    pages: 3",
                "    rows: 40",
                "    festivals: false",
                "    stays: false",
                "    concurrency: 2",
            ]
        ),
        encoding="utf-8",
    )
    region_config = regions_root / "gongju.yaml"
    region_config.write_text(
        "\n".join(
            [
                "region: 공주",
                "queries:",
                "  - 공주 관광지",
                "sources:",
                "  kakao:",
                "    pages: 7",
            ]
        ),
        encoding="utf-8",
    )

    args = SimpleNamespace(
        config=str(region_config),
        region=None,
        queries=["공주 사진 명소"],
        tour_keywords=None,
        output_root="custom-data",
        save_db=None,
        province="세종특별자치시",
        kakao_pages=9,
        kakao_size=None,
        kakao_concurrency=4,
        naver_pages=None,
        naver_display=None,
        naver_concurrency=None,
        naver_min_interval_seconds=None,
        naver_retry_attempts=None,
        tour_pages=None,
        tour_rows=None,
        tour_concurrency=None,
        tour_festivals=None,
        tour_stays=None,
        festival_start_date=None,
        festival_end_date=None,
    )

    config = _resolve_run_config(args)

    assert config.region == "공주"
    assert config.queries == ["공주 사진 명소"]
    assert config.output_root == "custom-data"
    assert config.province == "세종특별자치시"
    assert config.sources.kakao.pages == 9
    assert config.sources.kakao.concurrency == 4


@pytest.mark.parametrize(
    ("field_name", "field_value", "expected_message"),
    [
        ("kakao_size", 0, "--kakao-size must be a positive integer."),
        ("naver_display", 0, "--naver-display must be a positive integer."),
        ("tour_rows", -1, "--tour-rows must be a positive integer."),
        ("kakao_pages", 0, "--kakao-pages must be a positive integer."),
        ("naver_pages", -2, "--naver-pages must be a positive integer."),
        ("tour_pages", 0, "--tour-pages must be a positive integer."),
        ("kakao_concurrency", 0, "--kakao-concurrency must be a positive integer."),
        ("naver_concurrency", -1, "--naver-concurrency must be a positive integer."),
        ("tour_concurrency", 0, "--tour-concurrency must be a positive integer."),
    ],
)
def test_resolve_run_config_rejects_non_positive_collection_sizes_and_counts(
    tmp_path: Path,
    field_name: str,
    field_value: int,
    expected_message: str,
) -> None:
    region_config = tmp_path / "gongju.yaml"
    region_config.write_text("region: 공주\n", encoding="utf-8")

    args = SimpleNamespace(
        config=str(region_config),
        region=None,
        queries=None,
        tour_keywords=None,
        output_root=None,
        save_db=None,
        province=None,
        kakao_pages=None,
        kakao_size=None,
        kakao_concurrency=None,
        naver_pages=None,
        naver_display=None,
        naver_concurrency=None,
        naver_min_interval_seconds=None,
        naver_retry_attempts=None,
        tour_pages=None,
        tour_rows=None,
        tour_concurrency=None,
        tour_festivals=None,
        tour_stays=None,
        festival_start_date=None,
        festival_end_date=None,
    )
    setattr(args, field_name, field_value)

    with pytest.raises(SystemExit, match=expected_message):
        _resolve_run_config(args)


def test_resolve_tour_keywords_keeps_explicit_empty_list() -> None:
    run_config = CollectionRunConfig(
        region="공주",
        tour_keywords=[],
        sources=CollectionSourcesConfig(
            tour_api=TourApiCollectionConfig(enabled=True),
        ),
    )

    assert _resolve_tour_keywords(run_config) == []


def test_resolve_tour_keywords_defaults_region_only_when_unset() -> None:
    run_config = CollectionRunConfig(
        region="공주",
        tour_keywords=None,
        sources=CollectionSourcesConfig(
            tour_api=TourApiCollectionConfig(enabled=True),
        ),
    )

    assert _resolve_tour_keywords(run_config) == ["공주"]


def test_collect_tour_task_raises_for_unknown_task_type(tmp_path: Path) -> None:
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
            return []

        def search_stays(self, *, rows: int = 20, page: int = 1) -> list[dict[str, object]]:
            return []

    collector = PlaceCollector(
        kakao_client=None,
        naver_client=None,
        tour_client=FakeTourClient(),
        output_root=tmp_path,
    )

    try:
        collector._collect_tour_task(
            region_name="공주",
            task_type="mystery",
            task_value=None,
            rows=20,
            pages=1,
            festival_start_date=None,
            festival_end_date=None,
        )
    except ValueError as exc:
        assert str(exc) == "Unknown TourAPI task_type: mystery"
    else:
        raise AssertionError("Expected ValueError for unknown TourAPI task_type")
