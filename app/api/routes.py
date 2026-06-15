from fastapi import APIRouter

from app.schemas.travel_design import TravelDesignRequest, TravelDesignResponse
from app.services.agent import TravelDesignAgent

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/ai/travel-design/draft", response_model=TravelDesignResponse)
def create_travel_design_draft(request: TravelDesignRequest) -> TravelDesignResponse:
    return TravelDesignAgent().run(request)


@router.get("/schemas/travel-design/request")
def travel_design_request_schema() -> dict:
    return TravelDesignRequest.model_json_schema()


@router.get("/schemas/travel-design/response")
def travel_design_response_schema() -> dict:
    return TravelDesignResponse.model_json_schema()
