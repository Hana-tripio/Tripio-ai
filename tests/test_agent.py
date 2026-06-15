from app.schemas.travel_design import CompanionType, TravelDesignRequest
from app.services.agent import TravelDesignAgent
from app.services.rag import CandidatePlaceRetriever
from app.services.workflow import TravelDesignWorkflow


def test_retriever_returns_region_candidates() -> None:
    request = TravelDesignRequest(
        region_id=10,
        region_name="공주",
        days=2,
        budget=300_000,
        people_count=2,
        companion_type=CompanionType.FRIEND,
        style_tags=["힐링", "역사"],
    )

    places = CandidatePlaceRetriever().retrieve(request)

    assert places
    assert all(place.region_id == 10 for place in places)


def test_agent_returns_travel_etf_draft_report() -> None:
    request = TravelDesignRequest(
        region_id=10,
        region_name="공주",
        days=2,
        budget=300_000,
        people_count=2,
        companion_type=CompanionType.FRIEND,
        style_tags=["힐링", "역사"],
    )

    response = TravelDesignAgent().run(request)

    assert response.plan_summary.title
    assert len(response.itinerary_days) == 2
    assert response.budget_plan.total_budget == 300_000
    assert response.editable_actions


def test_langgraph_workflow_returns_travel_etf_draft_report() -> None:
    request = TravelDesignRequest(
        region_id=10,
        region_name="공주",
        days=2,
        budget=300_000,
        people_count=2,
        companion_type=CompanionType.FRIEND,
        style_tags=["힐링", "역사"],
    )

    response = TravelDesignWorkflow().run(request)

    assert response.plan_summary.region_name == "공주"
    assert len(response.itinerary_days) == 2
    assert response.recommendations
