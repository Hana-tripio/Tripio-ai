from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from app.schemas.travel_design import (
    BudgetPlan,
    CandidatePlace,
    ItineraryDay,
    TravelDesignRequest,
    TravelDesignResponse,
)
from app.services.budget import calculate_budget
from app.services.generator import build_metrics, build_plan_summary, generate_itinerary
from app.services.rag import CandidatePlaceRetriever
from app.services.validator import ValidationResult, validate_itinerary


class TravelDesignState(TypedDict, total=False):
    request: TravelDesignRequest
    candidate_places: list[CandidatePlace]
    itinerary_days: list[ItineraryDay]
    budget_plan: BudgetPlan
    validation: ValidationResult
    response: TravelDesignResponse


class TravelDesignWorkflow:
    def __init__(self, retriever: CandidatePlaceRetriever | None = None) -> None:
        self.retriever = retriever or CandidatePlaceRetriever()
        self.graph = self._build_graph()

    def run(self, request: TravelDesignRequest) -> TravelDesignResponse:
        result = cast(dict[str, Any], self.graph.invoke({"request": request}))
        response = result.get("response")

        if not isinstance(response, TravelDesignResponse):
            raise RuntimeError("TravelDesignWorkflow finished without a response")

        return response

    def _build_graph(self) -> Any:
        graph = StateGraph(TravelDesignState)

        graph.add_node("normalize_input", self._normalize_input)
        graph.add_node("retrieve_places", self._retrieve_places)
        graph.add_node("generate_plan", self._generate_plan)
        graph.add_node("plan_budget", self._plan_budget)
        graph.add_node("validate_plan", self._validate_plan)
        graph.add_node("compose_response", self._compose_response)

        graph.add_edge(START, "normalize_input")
        graph.add_edge("normalize_input", "retrieve_places")
        graph.add_edge("retrieve_places", "generate_plan")
        graph.add_edge("generate_plan", "plan_budget")
        graph.add_edge("plan_budget", "validate_plan")
        graph.add_edge("validate_plan", "compose_response")
        graph.add_edge("compose_response", END)

        return graph.compile()

    def _normalize_input(self, state: TravelDesignState) -> TravelDesignState:
        return {"request": state["request"]}

    def _retrieve_places(self, state: TravelDesignState) -> TravelDesignState:
        request = state["request"]
        return {"candidate_places": self.retriever.retrieve(request)}

    def _generate_plan(self, state: TravelDesignState) -> TravelDesignState:
        return {
            "itinerary_days": generate_itinerary(
                request=state["request"],
                candidate_places=state["candidate_places"],
            )
        }

    def _plan_budget(self, state: TravelDesignState) -> TravelDesignState:
        return {
            "budget_plan": calculate_budget(
                total_budget=state["request"].budget,
                itinerary_days=state["itinerary_days"],
            )
        }

    def _validate_plan(self, state: TravelDesignState) -> TravelDesignState:
        return {
            "validation": validate_itinerary(
                itinerary_days=state["itinerary_days"],
                candidate_places=state["candidate_places"],
                expected_days=state["request"].days,
                total_budget=state["request"].budget,
            )
        }

    def _compose_response(self, state: TravelDesignState) -> TravelDesignState:
        validation = state["validation"]
        warnings = list(validation.warnings)
        if not validation.valid:
            warnings.extend(validation.errors)

        return {
            "response": TravelDesignResponse(
                plan_summary=build_plan_summary(state["request"]),
                itinerary_days=state["itinerary_days"],
                budget_plan=state["budget_plan"],
                portfolio_metrics=build_metrics(state["itinerary_days"]),
                recommendations=[
                    "충청도 후보 장소와 사용자 조건을 바탕으로 생성한 Travel ETF 초안입니다.",
                    "최종 예산과 점수는 Spring Boot에서 한 번 더 검증해야 합니다.",
                ],
                warnings=warnings,
                editable_actions=[
                    "전체 다시 생성",
                    "Day만 다시 생성",
                    "장소 교체",
                    "예산 낮추기",
                    "로컬 소비 늘리기",
                ],
            )
        }
