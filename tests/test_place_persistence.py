from dataclasses import dataclass, field

from app.schemas.place_source import ExternalPlaceSource, NormalizedPlace, PlaceCategory
from app.services.place_persistence import PlacePersistenceService


@dataclass
class FakeRegion:
    province_name: str
    city_name: str
    latitude: float | None
    longitude: float | None


@dataclass
class FakePlace:
    region: FakeRegion
    name: str
    category: str
    address: str
    road_address: str
    latitude: float | None
    longitude: float | None
    phone: str
    url: str
    image_url: str
    description: str
    tags: list[str] = field(default_factory=list)


@dataclass
class FakeSource:
    place: FakePlace
    source: str
    external_id: str
    source_url: str
    raw_payload: dict[str, object]


class FakePlaceRepository:
    def __init__(self) -> None:
        self.regions: dict[tuple[str, str], FakeRegion] = {}
        self.places: list[FakePlace] = []
        self.sources: dict[tuple[str, str], FakeSource] = {}
        self.flushed = False

    def get_or_create_region(
        self,
        *,
        province_name: str,
        city_name: str,
        latitude: float | None,
        longitude: float | None,
    ) -> tuple[FakeRegion, bool]:
        key = (province_name, city_name)
        if key in self.regions:
            return self.regions[key], False
        region = FakeRegion(province_name, city_name, latitude, longitude)
        self.regions[key] = region
        return region, True

    def find_place_by_source(self, *, source: str, external_id: str) -> FakePlace | None:
        source_record = self.sources.get((source, external_id))
        if source_record:
            return source_record.place
        return None

    def find_place(self, *, region: FakeRegion, name: str, address: str) -> FakePlace | None:
        for place in self.places:
            if place.region == region and place.name == name and place.address == address:
                return place
        return None

    def create_place(
        self,
        *,
        region: FakeRegion,
        name: str,
        category: str,
        address: str,
        road_address: str,
        latitude: float | None,
        longitude: float | None,
        phone: str,
        url: str,
        image_url: str,
        description: str,
        tags: list[str],
    ) -> FakePlace:
        place = FakePlace(
            region=region,
            name=name,
            category=category,
            address=address,
            road_address=road_address,
            latitude=latitude,
            longitude=longitude,
            phone=phone,
            url=url,
            image_url=image_url,
            description=description,
            tags=tags,
        )
        self.places.append(place)
        return place

    def update_place(
        self,
        place: FakePlace,
        *,
        category: str,
        address: str,
        road_address: str,
        latitude: float | None,
        longitude: float | None,
        phone: str,
        url: str,
        image_url: str,
        description: str,
        tags: list[str],
    ) -> None:
        place.category = category
        place.address = address or place.address
        place.road_address = road_address or place.road_address
        place.latitude = latitude or place.latitude
        place.longitude = longitude or place.longitude
        place.phone = phone or place.phone
        place.url = url or place.url
        place.image_url = image_url or place.image_url
        place.description = description or place.description
        place.tags = tags

    def get_source(self, *, source: str, external_id: str) -> FakeSource | None:
        return self.sources.get((source, external_id))

    def create_source(
        self,
        *,
        place: FakePlace,
        source: str,
        external_id: str,
        source_url: str,
        raw_payload: dict[str, object],
    ) -> FakeSource:
        source_record = FakeSource(place, source, external_id, source_url, raw_payload)
        self.sources[(source, external_id)] = source_record
        return source_record

    def update_source(
        self,
        source_record: FakeSource,
        *,
        place: FakePlace,
        source_url: str,
        raw_payload: dict[str, object],
    ) -> None:
        source_record.place = place
        source_record.source_url = source_url
        source_record.raw_payload = raw_payload

    def flush(self) -> None:
        self.flushed = True


def test_persists_normalized_places_as_region_place_and_sources() -> None:
    repository = FakePlaceRepository()
    service = PlacePersistenceService(repository)
    place = NormalizedPlace(
        source=ExternalPlaceSource.KAKAO,
        source_place_id="kakao-1",
        name="공산성",
        region_name="공주",
        address="충남 공주시 웅진로 280",
        road_address="충남 공주시 웅진로 280",
        latitude=36.462293,
        longitude=127.125997,
        category=PlaceCategory.TOURIST_ATTRACTION,
        source_query="공주 관광지",
        phone="041-856-7700",
        url="https://place.map.kakao.com/1",
        tags=["관광지", "문화유적"],
        sources=[
            ExternalPlaceSource.KAKAO,
            ExternalPlaceSource.NAVER,
            ExternalPlaceSource.TOUR_API,
        ],
        source_place_ids=["kakao-1", "naver-1", "tour-1"],
    )

    summary = service.persist([place], province_name="충청남도")

    assert summary.regions_created == 1
    assert summary.places_created == 1
    assert summary.sources_created == 3
    assert repository.flushed is True
    assert repository.places[0].tags == ["관광지", "문화유적"]
    assert repository.sources[("KAKAO", "kakao-1")].raw_payload["source_query"] == "공주 관광지"


def test_persistence_updates_existing_source_without_duplicating_place() -> None:
    repository = FakePlaceRepository()
    service = PlacePersistenceService(repository)
    first = NormalizedPlace(
        source=ExternalPlaceSource.TOUR_API,
        source_place_id="tour-1",
        name="공산성",
        region_name="공주",
        address="충남 공주시 웅진로 280",
        latitude=36.462293,
        longitude=127.125997,
        category=PlaceCategory.TOURIST_ATTRACTION,
        source_query="공주",
        tags=["관광지"],
    )
    second = first.model_copy(update={"description": "공주 대표 관광지"})

    service.persist([first], province_name="충청남도")
    summary = service.persist([second], province_name="충청남도")

    assert summary.places_created == 0
    assert summary.places_updated == 1
    assert summary.sources_created == 0
    assert summary.sources_updated == 1
    assert len(repository.places) == 1
    assert repository.places[0].description == "공주 대표 관광지"
