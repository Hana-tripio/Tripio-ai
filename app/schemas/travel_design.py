from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class DesignMode(StrEnum):
    FULL_GENERATION = "FULL_GENERATION"
    PARTIAL_REGENERATION = "PARTIAL_REGENERATION"
    BUDGET_REBALANCE = "BUDGET_REBALANCE"
    PLACE_REPLACEMENT = "PLACE_REPLACEMENT"
    SCHEDULE_OPTIMIZATION = "SCHEDULE_OPTIMIZATION"


class CompanionType(StrEnum):
    SOLO = "SOLO"
    FRIEND = "FRIEND"
    COUPLE = "COUPLE"
    FAMILY = "FAMILY"
    GROUP = "GROUP"


class PlaceCategory(StrEnum):
    LODGING = "LODGING"
    RESTAURANT = "RESTAURANT"
    CAFE = "CAFE"
    ACTIVITY = "ACTIVITY"
    FESTIVAL = "FESTIVAL"
    MARKET = "MARKET"
    TRANSPORT = "TRANSPORT"
    ETC = "ETC"


class CandidatePlace(BaseModel):
    place_id: int = Field(gt=0)
    name: str = Field(min_length=1)
    region_id: int = Field(gt=0)
    category: PlaceCategory
    estimated_cost: int = Field(ge=0)
    average_stay_minutes: int = Field(gt=0)
    is_core_spot: bool = False
    is_local: bool = False
    tags: list[str] = Field(default_factory=list)
    description: str = ""
    trend_score: float = Field(default=0.0, ge=0.0)
    local_contribution_score: float = Field(default=0.0, ge=0.0)


class TravelDesignRequest(BaseModel):
    session_id: int | None = Field(default=None, gt=0)
    user_id: int | None = Field(default=None, gt=0)
    mode: DesignMode = DesignMode.FULL_GENERATION
    region_id: int = Field(gt=0)
    region_name: str = Field(min_length=1)
    days: int = Field(ge=1, le=10)
    budget: int = Field(ge=50_000)
    people_count: int = Field(ge=1, le=20)
    companion_type: CompanionType
    style_tags: list[str] = Field(default_factory=list)
    local_contribution_enabled: bool = True
    must_include_place_ids: list[int] = Field(default_factory=list)
    candidate_places: list[CandidatePlace] = Field(default_factory=list)
    personalization_enabled: bool = False

    @field_validator("style_tags")
    @classmethod
    def reject_empty_style_tags(cls, value: list[str]) -> list[str]:
        return [tag.strip() for tag in value if tag.strip()]


class ItineraryItem(BaseModel):
    place_id: int = Field(gt=0)
    place_name: str = Field(min_length=1)
    category: PlaceCategory
    sequence: int = Field(ge=1)
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    estimated_cost: int = Field(ge=0)
    is_core: bool = False
    is_local: bool = False
    reason: str = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)


class ItineraryDay(BaseModel):
    day_number: int = Field(ge=1)
    day_title: str = Field(min_length=1)
    items: list[ItineraryItem]


class CategoryBudget(BaseModel):
    category: PlaceCategory
    amount: int = Field(ge=0)
    ratio: float = Field(ge=0.0, le=100.0)


class BudgetPlan(BaseModel):
    total_budget: int = Field(ge=0)
    estimated_total_cost: int = Field(ge=0)
    remaining_budget: int
    category_budgets: list[CategoryBudget]


class PortfolioMetrics(BaseModel):
    local_contribution_score: float = Field(ge=0.0, le=100.0)
    region_value_score: float = Field(ge=0.0, le=100.0)
    expected_reward: int = Field(ge=0)
    core_spot_ratio: float = Field(ge=0.0, le=100.0)
    local_spend_ratio: float = Field(ge=0.0, le=100.0)
    schedule_density: Literal["RELAXED", "BALANCED", "DENSE"]
    budget_stability: Literal["LOW", "MEDIUM", "HIGH"]


class PlanSummary(BaseModel):
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    region_id: int = Field(gt=0)
    region_name: str = Field(min_length=1)
    duration_days: int = Field(ge=1)
    people_count: int = Field(ge=1)
    companion_type: CompanionType
    style_tags: list[str]
    local_contribution_enabled: bool


class TravelDesignResponse(BaseModel):
    plan_summary: PlanSummary
    itinerary_days: list[ItineraryDay]
    budget_plan: BudgetPlan
    portfolio_metrics: PortfolioMetrics
    recommendations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    editable_actions: list[str] = Field(default_factory=list)
    personalization_reasons: list[str] = Field(default_factory=list)
