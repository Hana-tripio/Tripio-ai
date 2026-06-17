from dataclasses import dataclass
from typing import Any, Protocol

from app.schemas.place_source import ExternalPlaceSource, NormalizedPlace


@dataclass(frozen=True)
class PlacePersistenceSummary:
    regions_created: int = 0
    places_created: int = 0
    places_updated: int = 0
    sources_created: int = 0
    sources_updated: int = 0


class PlaceRepository(Protocol):
    def get_or_create_region(
        self,
        *,
        province_name: str,
        city_name: str,
        latitude: float | None,
        longitude: float | None,
    ) -> tuple[Any, bool]:
        pass

    def find_place_by_source(self, *, source: str, external_id: str) -> Any | None:
        pass

    def find_place(self, *, region: Any, name: str, address: str) -> Any | None:
        pass

    def create_place(
        self,
        *,
        region: Any,
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
    ) -> Any:
        pass

    def update_place(
        self,
        place: Any,
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
        pass

    def get_source(self, *, source: str, external_id: str) -> Any | None:
        pass

    def create_source(
        self,
        *,
        place: Any,
        source: str,
        external_id: str,
        source_url: str,
        raw_payload: dict[str, object],
    ) -> Any:
        pass

    def update_source(
        self,
        source_record: Any,
        *,
        place: Any,
        source_url: str,
        raw_payload: dict[str, object],
    ) -> None:
        pass

    def flush(self) -> None:
        pass


class PlacePersistenceService:
    def __init__(self, repository: PlaceRepository) -> None:
        self.repository = repository

    def persist(
        self,
        places: list[NormalizedPlace],
        *,
        province_name: str,
    ) -> PlacePersistenceSummary:
        regions_created = 0
        places_created = 0
        places_updated = 0
        sources_created = 0
        sources_updated = 0

        for normalized_place in places:
            region, created_region = self.repository.get_or_create_region(
                province_name=province_name,
                city_name=normalized_place.region_name,
                latitude=normalized_place.latitude,
                longitude=normalized_place.longitude,
            )
            regions_created += int(created_region)

            source_pairs = _source_pairs(normalized_place)
            place = _first_existing_source_place(self.repository, source_pairs)
            if place is None:
                place = self.repository.find_place(
                    region=region,
                    name=normalized_place.name,
                    address=normalized_place.address,
                )

            if place is None:
                place = self.repository.create_place(
                    region=region,
                    name=normalized_place.name,
                    category=str(normalized_place.category),
                    address=normalized_place.address,
                    road_address=normalized_place.road_address,
                    latitude=normalized_place.latitude,
                    longitude=normalized_place.longitude,
                    phone=normalized_place.phone,
                    url=normalized_place.url,
                    image_url=normalized_place.image_url,
                    description=normalized_place.description,
                    tags=normalized_place.tags,
                )
                places_created += 1
            else:
                self.repository.update_place(
                    place,
                    category=str(normalized_place.category),
                    address=normalized_place.address,
                    road_address=normalized_place.road_address,
                    latitude=normalized_place.latitude,
                    longitude=normalized_place.longitude,
                    phone=normalized_place.phone,
                    url=normalized_place.url,
                    image_url=normalized_place.image_url,
                    description=normalized_place.description,
                    tags=normalized_place.tags,
                )
                places_updated += 1

            for source, external_id in source_pairs:
                raw_payload = _raw_payload(normalized_place, source=source, external_id=external_id)
                source_record = self.repository.get_source(
                    source=source.value,
                    external_id=external_id,
                )
                if source_record is None:
                    self.repository.create_source(
                        place=place,
                        source=source.value,
                        external_id=external_id,
                        source_url=normalized_place.url,
                        raw_payload=raw_payload,
                    )
                    sources_created += 1
                else:
                    self.repository.update_source(
                        source_record,
                        place=place,
                        source_url=normalized_place.url,
                        raw_payload=raw_payload,
                    )
                    sources_updated += 1

        self.repository.flush()
        return PlacePersistenceSummary(
            regions_created=regions_created,
            places_created=places_created,
            places_updated=places_updated,
            sources_created=sources_created,
            sources_updated=sources_updated,
        )


def _first_existing_source_place(
    repository: PlaceRepository,
    source_pairs: list[tuple[ExternalPlaceSource, str]],
) -> Any | None:
    for source, external_id in source_pairs:
        place = repository.find_place_by_source(source=source.value, external_id=external_id)
        if place is not None:
            return place
    return None


def _source_pairs(place: NormalizedPlace) -> list[tuple[ExternalPlaceSource, str]]:
    pairs: list[tuple[ExternalPlaceSource, str]] = []
    source_ids = place.source_place_ids or [place.source_place_id]
    for index, source in enumerate(place.sources or [place.source]):
        external_id = source_ids[index] if index < len(source_ids) else ""
        pairs.append((source, external_id or _fallback_external_id(place, source)))
    return pairs


def _fallback_external_id(place: NormalizedPlace, source: ExternalPlaceSource) -> str:
    return f"{source.value}:{place.region_name}:{place.name}:{place.address}"


def _raw_payload(
    place: NormalizedPlace,
    *,
    source: ExternalPlaceSource,
    external_id: str,
) -> dict[str, object]:
    payload = place.model_dump(mode="json")
    payload["source"] = source.value
    payload["source_place_id"] = external_id
    return payload
