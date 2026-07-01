import argparse
from dataclasses import replace
from pathlib import Path

from app.clients.kakao_local_client import KakaoLocalClient
from app.clients.naver_local_client import NaverLocalClient
from app.clients.tour_api_client import TourApiClient
from app.core.collection_config import (
    CollectionRunConfig,
    load_collection_run_config,
    replace_run_config,
)
from app.core.config import settings
from app.data.collection_queries import SUPPORTED_QUERY_REGIONS, build_queries
from app.db.place_repository import SqlAlchemyPlaceRepository
from app.db.session import SessionLocal
from app.services.place_collector import PlaceCollector
from app.services.place_persistence import PlacePersistenceService


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    run_config = _resolve_run_config(args)

    _validate_required_settings(run_config)

    queries = run_config.queries or _default_queries_for_region(run_config.region)
    tour_keywords = _resolve_tour_keywords(run_config)

    collector = PlaceCollector(
        kakao_client=(
            KakaoLocalClient(api_key=settings.kakao_rest_api_key)
            if run_config.sources.kakao.enabled
            else None
        ),
        naver_client=(
            NaverLocalClient(
                client_id=settings.naver_client_id,
                client_secret=settings.naver_client_secret,
                retry_attempts=run_config.sources.naver.retry_attempts,
                min_interval_seconds=run_config.sources.naver.min_interval_seconds,
            )
            if run_config.sources.naver.enabled
            else None
        ),
        tour_client=(
            TourApiClient(service_key=settings.tour_api_service_key)
            if run_config.sources.tour_api.enabled
            else None
        ),
        output_root=Path(run_config.output_root),
    )
    result = collector.collect(
        region_name=run_config.region,
        queries=queries,
        tour_keywords=tour_keywords,
        kakao_size=run_config.sources.kakao.size,
        naver_display=run_config.sources.naver.display,
        tour_rows=run_config.sources.tour_api.rows,
        kakao_pages=run_config.sources.kakao.pages,
        naver_pages=run_config.sources.naver.pages,
        tour_pages=run_config.sources.tour_api.pages,
        include_tour_festivals=run_config.sources.tour_api.festivals,
        include_tour_stays=run_config.sources.tour_api.stays,
        festival_start_date=run_config.festival_start_date,
        festival_end_date=run_config.festival_end_date,
        kakao_concurrency=run_config.sources.kakao.concurrency,
        naver_concurrency=run_config.sources.naver.concurrency,
        tour_concurrency=run_config.sources.tour_api.concurrency,
    )

    _print_collection_summary(result, Path(run_config.output_root).resolve())

    if run_config.save_db:
        with SessionLocal() as session:
            repository = SqlAlchemyPlaceRepository(session)
            summary = PlacePersistenceService(repository).persist(
                result.processed_places,
                province_name=run_config.province,
            )
            session.commit()
        print(f"db_regions_created={summary.regions_created}")
        print(f"db_places_created={summary.places_created}")
        print(f"db_places_updated={summary.places_updated}")
        print(f"db_sources_created={summary.sources_created}")
        print(f"db_sources_updated={summary.sources_updated}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect Tripio place data from Kakao/Naver APIs.")
    parser.add_argument("--config", help="Collection YAML config path.")
    parser.add_argument("--region", help="Region name, e.g. 공주")
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="Search query. Can be passed multiple times.",
    )
    parser.add_argument(
        "--tour-keyword",
        action="append",
        dest="tour_keywords",
        help="TourAPI keyword. Can be passed multiple times.",
    )
    parser.add_argument(
        "--output-root",
        help="Output root directory. Defaults to the config value or ./data",
    )
    parser.add_argument(
        "--save-db",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Persist processed places into PostgreSQL after collection.",
    )
    parser.add_argument(
        "--province",
        help="Province name used when persisting region records.",
    )
    parser.add_argument("--kakao-pages", type=int, help="Number of Kakao pages per query.")
    parser.add_argument("--kakao-size", type=int, help="Number of Kakao results per page.")
    parser.add_argument("--kakao-concurrency", type=int, help="Concurrent Kakao query workers.")
    parser.add_argument("--naver-pages", type=int, help="Number of Naver pages per query.")
    parser.add_argument("--naver-display", type=int, help="Number of Naver results per page.")
    parser.add_argument("--naver-concurrency", type=int, help="Concurrent Naver query workers.")
    parser.add_argument(
        "--naver-min-interval-seconds",
        type=float,
        help="Minimum delay between sequential Naver requests.",
    )
    parser.add_argument(
        "--naver-retry-attempts",
        type=int,
        help="Retry count for Naver 429 responses.",
    )
    parser.add_argument("--tour-pages", type=int, help="Number of TourAPI pages per request.")
    parser.add_argument("--tour-rows", type=int, help="Rows per TourAPI request.")
    parser.add_argument("--tour-concurrency", type=int, help="Concurrent TourAPI workers.")
    parser.add_argument(
        "--tour-festivals",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Collect TourAPI festival data for the configured date range.",
    )
    parser.add_argument(
        "--tour-stays",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Collect TourAPI stay data in addition to keyword results.",
    )
    parser.add_argument("--festival-start-date", help="Festival start date in YYYYMMDD format.")
    parser.add_argument("--festival-end-date", help="Festival end date in YYYYMMDD format.")
    return parser


def _resolve_run_config(args: argparse.Namespace) -> CollectionRunConfig:
    config = load_collection_run_config(args.config) if args.config else CollectionRunConfig()
    region = args.region or config.region
    if not region:
        raise SystemExit("Region must be provided via --region or config file.")

    sources = config.sources
    sources = replace(
        sources,
        kakao=replace(
            sources.kakao,
            pages=_require_positive_int(
                "--kakao-pages",
                args.kakao_pages if args.kakao_pages is not None else sources.kakao.pages,
            ),
            size=_require_positive_int(
                "--kakao-size",
                args.kakao_size if args.kakao_size is not None else sources.kakao.size,
            ),
            concurrency=(
                _require_positive_int("--kakao-concurrency", args.kakao_concurrency)
                if args.kakao_concurrency is not None
                else _require_positive_int("--kakao-concurrency", sources.kakao.concurrency)
            ),
        ),
        naver=replace(
            sources.naver,
            pages=_require_positive_int(
                "--naver-pages",
                args.naver_pages if args.naver_pages is not None else sources.naver.pages,
            ),
            display=_require_positive_int(
                "--naver-display",
                args.naver_display if args.naver_display is not None else sources.naver.display,
            ),
            concurrency=(
                _require_positive_int("--naver-concurrency", args.naver_concurrency)
                if args.naver_concurrency is not None
                else _require_positive_int("--naver-concurrency", sources.naver.concurrency)
            ),
            min_interval_seconds=(
                args.naver_min_interval_seconds
                if args.naver_min_interval_seconds is not None
                else sources.naver.min_interval_seconds
            ),
            retry_attempts=(
                max(0, args.naver_retry_attempts)
                if args.naver_retry_attempts is not None
                else sources.naver.retry_attempts
            ),
        ),
        tour_api=replace(
            sources.tour_api,
            pages=_require_positive_int(
                "--tour-pages",
                args.tour_pages if args.tour_pages is not None else sources.tour_api.pages,
            ),
            rows=_require_positive_int(
                "--tour-rows",
                args.tour_rows if args.tour_rows is not None else sources.tour_api.rows,
            ),
            concurrency=(
                _require_positive_int("--tour-concurrency", args.tour_concurrency)
                if args.tour_concurrency is not None
                else _require_positive_int("--tour-concurrency", sources.tour_api.concurrency)
            ),
            festivals=(
                args.tour_festivals
                if args.tour_festivals is not None
                else sources.tour_api.festivals
            ),
            stays=args.tour_stays if args.tour_stays is not None else sources.tour_api.stays,
        ),
    )
    return replace_run_config(
        config,
        region=region,
        province=args.province or config.province,
        output_root=args.output_root or config.output_root,
        save_db=args.save_db if args.save_db is not None else config.save_db,
        queries=args.queries if args.queries is not None else config.queries,
        tour_keywords=(
            args.tour_keywords if args.tour_keywords is not None else config.tour_keywords
        ),
        festival_start_date=args.festival_start_date or config.festival_start_date,
        festival_end_date=args.festival_end_date or config.festival_end_date,
        sources=sources,
    )


def _print_collection_summary(result, output_root: Path | str) -> None:
    print(f"region={result.region_name}")
    print(f"queries={len(result.queries)}")
    print(f"processed_places={len(result.processed_places)}")
    print(f"quality_input={result.quality_summary.input_count}")
    print(f"quality_kept={result.quality_summary.kept_count}")
    print(f"quality_filtered={result.quality_summary.filtered_count}")
    print(f"quality_reclassified={result.quality_summary.reclassified_count}")
    print(f"output={output_root}")
    if result.warnings:
        print(f"warnings_count={len(result.warnings)}")
        for warning in result.warnings:
            print(f"warning={warning}")


def _resolve_tour_keywords(run_config: CollectionRunConfig) -> list[str] | None:
    if run_config.tour_keywords is not None:
        return run_config.tour_keywords
    if run_config.sources.tour_api.enabled and run_config.region:
        return [run_config.region]
    return None


def _require_positive_int(option_name: str, value: int) -> int:
    if value <= 0:
        raise SystemExit(f"{option_name} must be a positive integer.")
    return value


def _validate_required_settings(run_config: CollectionRunConfig) -> None:
    missing = []
    if run_config.sources.kakao.enabled and not settings.kakao_rest_api_key:
        missing.append("KAKAO_REST_API_KEY")
    if run_config.sources.naver.enabled and not settings.naver_client_id:
        missing.append("NAVER_CLIENT_ID")
    if run_config.sources.naver.enabled and not settings.naver_client_secret:
        missing.append("NAVER_CLIENT_SECRET")
    if run_config.sources.tour_api.enabled and not settings.tour_api_service_key:
        missing.append("TOUR_API_SERVICE_KEY")
    if missing:
        raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")


def _default_queries_for_region(region_name: str | None) -> list[str]:
    if not region_name:
        raise SystemExit("Region must be provided before building default queries.")
    if region_name in SUPPORTED_QUERY_REGIONS:
        return build_queries(region_name)
    return [f"{region_name} 관광지", f"{region_name} 카페", f"{region_name} 맛집"]


if __name__ == "__main__":
    main()
