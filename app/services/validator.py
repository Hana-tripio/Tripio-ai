from dataclasses import dataclass

from app.schemas.travel_design import CandidatePlace, ItineraryDay


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]


def validate_itinerary(
    itinerary_days: list[ItineraryDay],
    candidate_places: list[CandidatePlace],
    expected_days: int,
    total_budget: int,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    candidate_ids = {place.place_id for place in candidate_places}
    total_cost = 0

    if len(itinerary_days) != expected_days:
        errors.append("DAY_COUNT_MISMATCH")

    for day in itinerary_days:
        sequences = [item.sequence for item in day.items]
        if sequences != sorted(sequences):
            errors.append(f"DAY_{day.day_number}_SEQUENCE_NOT_SORTED")

        for item in day.items:
            total_cost += item.estimated_cost
            if item.place_id not in candidate_ids:
                errors.append(f"UNKNOWN_PLACE_ID:{item.place_id}")
            if item.start_time >= item.end_time:
                errors.append(f"INVALID_TIME_RANGE:{item.place_id}")

    if total_cost > total_budget:
        warnings.append("BUDGET_EXCEEDED")

    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)
