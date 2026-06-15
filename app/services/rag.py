from app.data.seed_places import SEED_PLACES
from app.schemas.travel_design import CandidatePlace, TravelDesignRequest


class CandidatePlaceRetriever:
    def retrieve(self, request: TravelDesignRequest) -> list[CandidatePlace]:
        candidates = request.candidate_places or SEED_PLACES
        region_matches = [place for place in candidates if place.region_id == request.region_id]
        return sorted(
            region_matches,
            key=lambda place: (place.trend_score, place.local_contribution_score),
            reverse=True,
        )[:40]
