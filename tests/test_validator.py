from app.schemas.travel_design import (
    CompanionType,
    ItineraryDay,
    ItineraryItem,
    PlaceCategory,
    TravelDesignRequest,
)
from app.services.validator import validate_itinerary


def test_travel_design_request_trims_empty_style_tags() -> None:
    request = TravelDesignRequest(
        region_id=10,
        region_name="공주",
        days=2,
        budget=300_000,
        people_count=2,
        companion_type=CompanionType.FRIEND,
        style_tags=["힐링", " ", "역사"],
    )

    assert request.style_tags == ["힐링", "역사"]


def test_validator_rejects_unknown_place_id() -> None:
    item = ItineraryItem(
        place_id=999,
        place_name="없는 장소",
        category=PlaceCategory.ACTIVITY,
        sequence=1,
        start_time="10:00",
        end_time="11:00",
        estimated_cost=1_000,
        reason="테스트",
    )
    day = ItineraryDay(day_number=1, day_title="테스트 Day", items=[item])

    result = validate_itinerary(
        itinerary_days=[day],
        candidate_places=[],
        expected_days=1,
        total_budget=100_000,
    )

    assert not result.valid
    assert "UNKNOWN_PLACE_ID:999" in result.errors
