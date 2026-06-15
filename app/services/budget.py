from collections import defaultdict

from app.schemas.travel_design import BudgetPlan, CategoryBudget, ItineraryDay, PlaceCategory


def calculate_budget(total_budget: int, itinerary_days: list[ItineraryDay]) -> BudgetPlan:
    category_totals: dict[PlaceCategory, int] = defaultdict(int)
    estimated_total = 0

    for day in itinerary_days:
        for item in day.items:
            estimated_total += item.estimated_cost
            category_totals[item.category] += item.estimated_cost

    category_budgets = [
        CategoryBudget(
            category=category,
            amount=amount,
            ratio=round((amount / estimated_total) * 100, 2) if estimated_total else 0.0,
        )
        for category, amount in category_totals.items()
    ]

    return BudgetPlan(
        total_budget=total_budget,
        estimated_total_cost=estimated_total,
        remaining_budget=total_budget - estimated_total,
        category_budgets=category_budgets,
    )
