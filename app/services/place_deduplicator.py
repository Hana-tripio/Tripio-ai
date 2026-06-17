import re

from app.schemas.place_source import ExternalPlaceSource, NormalizedPlace


def deduplicate_places(places: list[NormalizedPlace]) -> list[NormalizedPlace]:
    merged: dict[str, NormalizedPlace] = {}

    for place in places:
        key = _dedupe_key(place)
        existing = merged.get(key)
        if existing is None:
            merged[key] = place.model_copy(deep=True)
            continue

        existing.sources = _append_unique_sources(existing.sources, place.sources)
        existing.source_place_ids = _append_unique_strings(
            existing.source_place_ids,
            place.source_place_ids,
        )
        existing.tags = _append_unique_strings(existing.tags, place.tags)
        if not existing.description and place.description:
            existing.description = place.description
        if not existing.phone and place.phone:
            existing.phone = place.phone
        if not existing.url and place.url:
            existing.url = place.url

    return list(merged.values())


def _dedupe_key(place: NormalizedPlace) -> str:
    name = _normalize_text(place.name)
    address = _normalize_text(place.road_address or place.address)
    if address:
        return f"{name}:{address}"
    return f"{name}:{round(place.latitude, 4)}:{round(place.longitude, 4)}"


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _append_unique_sources(
    left: list[ExternalPlaceSource],
    right: list[ExternalPlaceSource],
) -> list[ExternalPlaceSource]:
    values = list(left)
    for item in right:
        if item not in values:
            values.append(item)
    return values


def _append_unique_strings(left: list[str], right: list[str]) -> list[str]:
    values = list(left)
    for item in right:
        if item and item not in values:
            values.append(item)
    return values

