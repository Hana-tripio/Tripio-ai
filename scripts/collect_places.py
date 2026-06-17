import argparse
from pathlib import Path

from app.clients.kakao_local_client import KakaoLocalClient
from app.clients.naver_local_client import NaverLocalClient
from app.clients.tour_api_client import TourApiClient
from app.core.config import settings
from app.db.place_repository import SqlAlchemyPlaceRepository
from app.db.session import SessionLocal
from app.services.place_collector import PlaceCollector
from app.services.place_persistence import PlacePersistenceService

DEFAULT_QUERIES_BY_REGION = {
    "공주": ["공주 관광지", "공주 카페", "공주 맛집", "공주 시장", "공주 숙소"],
    "대전": ["대전 관광지", "대전 카페", "대전 맛집", "대전 시장", "대전 숙소"],
    "청주": ["청주 관광지", "청주 카페", "청주 맛집", "청주 시장", "청주 숙소"],
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Tripio place data from Kakao/Naver APIs.")
    parser.add_argument("--region", required=True, help="Region name, e.g. 공주")
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
        default="data",
        help="Output root directory. Defaults to ./data",
    )
    parser.add_argument(
        "--save-db",
        action="store_true",
        help="Persist processed places into PostgreSQL after collection.",
    )
    parser.add_argument(
        "--province",
        default="충청남도",
        help="Province name used when persisting region records. Defaults to 충청남도.",
    )
    args = parser.parse_args()

    _validate_required_settings()

    queries = args.queries or DEFAULT_QUERIES_BY_REGION.get(
        args.region,
        [f"{args.region} 관광지", f"{args.region} 카페", f"{args.region} 맛집"],
    )
    tour_keywords = args.tour_keywords or [args.region]

    collector = PlaceCollector(
        kakao_client=KakaoLocalClient(api_key=settings.kakao_rest_api_key),
        naver_client=NaverLocalClient(
            client_id=settings.naver_client_id,
            client_secret=settings.naver_client_secret,
        ),
        tour_client=TourApiClient(service_key=settings.tour_api_service_key),
        output_root=Path(args.output_root),
    )
    result = collector.collect(
        region_name=args.region,
        queries=queries,
        tour_keywords=tour_keywords,
    )

    print(f"region={result.region_name}")
    print(f"queries={len(result.queries)}")
    print(f"processed_places={len(result.processed_places)}")
    print(f"output={Path(args.output_root).resolve()}")

    if args.save_db:
        with SessionLocal() as session:
            repository = SqlAlchemyPlaceRepository(session)
            summary = PlacePersistenceService(repository).persist(
                result.processed_places,
                province_name=args.province,
            )
            session.commit()
        print(f"db_regions_created={summary.regions_created}")
        print(f"db_places_created={summary.places_created}")
        print(f"db_places_updated={summary.places_updated}")
        print(f"db_sources_created={summary.sources_created}")
        print(f"db_sources_updated={summary.sources_updated}")


def _validate_required_settings() -> None:
    missing = []
    if not settings.kakao_rest_api_key:
        missing.append("KAKAO_REST_API_KEY")
    if not settings.naver_client_id:
        missing.append("NAVER_CLIENT_ID")
    if not settings.naver_client_secret:
        missing.append("NAVER_CLIENT_SECRET")
    if not settings.tour_api_service_key:
        missing.append("TOUR_API_SERVICE_KEY")
    if missing:
        raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")


if __name__ == "__main__":
    main()
