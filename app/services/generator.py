from app.schemas.travel_design import (
    CandidatePlace,
    ItineraryDay,
    ItineraryItem,
    PlanSummary,
    PortfolioMetrics,
    TravelDesignRequest,
)


def generate_itinerary(
    request: TravelDesignRequest,
    candidate_places: list[CandidatePlace],
) -> list[ItineraryDay]:
    selected = candidate_places[: max(request.days * 2, 1)]
    days: list[ItineraryDay] = []

    for day_number in range(1, request.days + 1):
        day_places = selected[(day_number - 1) * 2 : day_number * 2]
        items = [
            ItineraryItem(
                place_id=place.place_id,
                place_name=place.name,
                category=place.category,
                sequence=index,
                start_time=f"{9 + (index - 1) * 3:02d}:00",
                end_time=f"{11 + (index - 1) * 3:02d}:00",
                estimated_cost=place.estimated_cost * request.people_count,
                is_core=place.is_core_spot,
                is_local=place.is_local,
                reason=f"{', '.join(place.tags[:2])} 조건에 맞는 충청도 후보 장소입니다.",
            )
            for index, place in enumerate(day_places, start=1)
        ]
        days.append(
            ItineraryDay(
                day_number=day_number,
                day_title=f"Day {day_number} {request.region_name} 여행",
                items=items,
            )
        )

    return days


def build_plan_summary(request: TravelDesignRequest) -> PlanSummary:
    tag_text = " ".join(request.style_tags[:2]) or "맞춤"
    return PlanSummary(
        title=f"{request.region_name} {tag_text} Travel ETF",
        summary=(
            f"{request.region_name} 지역의 취향, 예산, "
            "지역상생 요소를 반영한 Travel ETF 초안입니다."
        ),
        region_id=request.region_id,
        region_name=request.region_name,
        duration_days=request.days,
        people_count=request.people_count,
        companion_type=request.companion_type,
        style_tags=request.style_tags,
        local_contribution_enabled=request.local_contribution_enabled,
    )


def build_metrics(itinerary_days: list[ItineraryDay]) -> PortfolioMetrics:
    items = [item for day in itinerary_days for item in day.items]
    core_count = sum(1 for item in items if item.is_core)
    local_cost = sum(item.estimated_cost for item in items if item.is_local)
    total_cost = sum(item.estimated_cost for item in items)

    core_ratio = round((core_count / len(items)) * 100, 2) if items else 0.0
    local_spend_ratio = round((local_cost / total_cost) * 100, 2) if total_cost else 0.0

    return PortfolioMetrics(
        local_contribution_score=min(100.0, 50.0 + local_spend_ratio),
        region_value_score=min(100.0, 60.0 + core_ratio / 2),
        expected_reward=int(local_cost * 0.03),
        core_spot_ratio=core_ratio,
        local_spend_ratio=local_spend_ratio,
        schedule_density="BALANCED",
        budget_stability="MEDIUM",
    )
