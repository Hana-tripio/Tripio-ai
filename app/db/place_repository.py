from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Place, PlaceSource, Region


class SqlAlchemyPlaceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_region(
        self,
        *,
        province_name: str,
        city_name: str,
        latitude: float | None,
        longitude: float | None,
    ) -> tuple[Region, bool]:
        region = self.session.scalar(
            select(Region).where(
                Region.province_name == province_name,
                Region.city_name == city_name,
            )
        )
        if region is not None:
            return region, False

        region = Region(
            province_name=province_name,
            city_name=city_name,
            latitude=latitude,
            longitude=longitude,
        )
        self.session.add(region)
        self.session.flush()
        return region, True

    def find_place_by_source(self, *, source: str, external_id: str) -> Place | None:
        source_record = self.session.scalar(
            select(PlaceSource).where(
                PlaceSource.source == source,
                PlaceSource.external_id == external_id,
            )
        )
        if source_record is None:
            return None
        return source_record.place

    def find_place(self, *, region: Region, name: str, address: str) -> Place | None:
        return self.session.scalar(
            select(Place).where(
                Place.region_id == region.id,
                Place.name == name,
                Place.address == address,
            )
        )

    def create_place(
        self,
        *,
        region: Region,
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
    ) -> Place:
        place = Place(
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
        self.session.add(place)
        self.session.flush()
        return place

    def update_place(
        self,
        place: Place,
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
        place.tags = _merge_tags(place.tags, tags)

    def get_source(self, *, source: str, external_id: str) -> PlaceSource | None:
        return self.session.scalar(
            select(PlaceSource).where(
                PlaceSource.source == source,
                PlaceSource.external_id == external_id,
            )
        )

    def create_source(
        self,
        *,
        place: Place,
        source: str,
        external_id: str,
        source_url: str,
        raw_payload: dict[str, object],
    ) -> PlaceSource:
        source_record = PlaceSource(
            place=place,
            source=source,
            external_id=external_id,
            source_url=source_url,
            raw_payload=raw_payload,
        )
        self.session.add(source_record)
        return source_record

    def update_source(
        self,
        source_record: PlaceSource,
        *,
        place: Place,
        source_url: str,
        raw_payload: dict[str, object],
    ) -> None:
        source_record.place = place
        source_record.source_url = source_url or source_record.source_url
        source_record.raw_payload = raw_payload

    def flush(self) -> None:
        self.session.flush()


def _merge_tags(current_tags: list[str] | None, new_tags: list[str]) -> list[str]:
    merged: list[str] = []
    for tag in [*(current_tags or []), *new_tags]:
        if tag not in merged:
            merged.append(tag)
    return merged
