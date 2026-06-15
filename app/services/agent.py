from app.schemas.travel_design import TravelDesignRequest, TravelDesignResponse
from app.services.rag import CandidatePlaceRetriever
from app.services.workflow import TravelDesignWorkflow


class TravelDesignAgent:
    def __init__(self, retriever: CandidatePlaceRetriever | None = None) -> None:
        self.workflow = TravelDesignWorkflow(retriever=retriever)

    def run(self, request: TravelDesignRequest) -> TravelDesignResponse:
        return self.workflow.run(request)
