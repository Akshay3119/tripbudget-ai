import re
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CITY = Literal["NYC", "PHL", "DC"]
DIETS = Literal["vegetarian", "vegan", "unrestricted"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Traveler(StrictModel):
    id: str = Field(pattern=r"^t[1-6]$")
    budget_cents: int = Field(ge=5000, le=1000000, strict=True)
    diet: DIETS = "unrestricted"
    maximum_walk_meters: int = Field(default=12000, ge=500, le=40000, strict=True)


class Preferences(StrictModel):
    diet: DIETS = "unrestricted"
    maximum_walk_meters: int = Field(default=12000, ge=500, le=40000, strict=True)
    preferred_categories: list[Literal["history", "museum", "park", "viewpoint"]] = Field(
        default_factory=list, max_length=4
    )


class PreferenceConfirmation(StrictModel):
    group_id: str = Field(default="demo-group", pattern=r"^[a-zA-Z0-9_-]{1,50}$")
    expected_version: int = Field(default=0, ge=0, strict=True)
    values: Preferences
    confirmed: Literal[True]


class TripRequest(StrictModel):
    start_date: date
    days: int = Field(default=5, ge=3, le=7, strict=True)
    cities: list[CITY] = Field(default_factory=lambda: ["NYC", "PHL", "DC"], min_length=1, max_length=3)
    travelers: list[Traveler] = Field(min_length=2, max_length=6)
    group_budget_cents: int | None = Field(default=None, ge=10000, le=6000000, strict=True)
    group_id: str = Field(default="demo-group", pattern=r"^[a-zA-Z0-9_-]{1,50}$")
    meal_cents: int = Field(default=1800, ge=500, le=20000, strict=True)
    lodging_standard_cents: int = Field(default=21000, ge=2000, le=150000, strict=True)
    lodging_economy_cents: int = Field(default=11000, ge=2000, le=150000, strict=True)
    room_capacity: int = Field(default=2, ge=1, le=4, strict=True)
    estimates_confirmed: Literal[True]
    request: str = Field(default="A balanced trip with history, parks and museums.", max_length=2000)
    required_activities: list[str] = Field(default_factory=list, max_length=10)
    wishlist: list[str] = Field(default_factory=list, max_length=10)
    use_saved_preferences: bool = True
    gateway_start_hour: int = Field(default=8, ge=0, le=12, strict=True)
    gateway_end_hour: int = Field(default=21, ge=15, le=23, strict=True)

    @model_validator(mode="after")
    def consistent(self):
        if len(set(self.cities)) != len(self.cities) or len(self.cities) > self.days:
            raise ValueError("Use unique cities with at least one day per city")
        if len({t.id for t in self.travelers}) != len(self.travelers):
            raise ValueError("Traveler IDs must be unique")
        if not date.today() < self.start_date <= date.today() + timedelta(days=90):
            raise ValueError("Start date must be tomorrow through 90 days ahead")
        for value in [*self.required_activities, *self.wishlist]:
            if not re.fullmatch(r"[a-z0-9_-]{2,60}", value):
                raise ValueError("Use catalog activity IDs")
        return self


class CostItem(StrictModel):
    id: str
    category: Literal["lodging", "meals", "local_transit", "intercity", "activity"]
    day: int
    city: CITY
    description: str
    unit_cents: int = Field(ge=0, strict=True)
    quantity: int = Field(ge=1, strict=True)
    total_cents: int = Field(ge=0, strict=True)
    beneficiaries: list[str]
    allocations: dict[str, int]
    evidence_state: Literal["VERIFIED_SNAPSHOT", "USER_ESTIMATE"]
    fact_id: str | None = None
    estimate_id: str | None = None
    taxes_included: Literal[True] = True


class ScheduledItem(StrictModel):
    id: str
    activity_id: str
    day: int
    city: CITY
    start: datetime
    end: datetime
    opening_start: datetime
    opening_end: datetime
    transfer_minutes: int = Field(ge=0)
    buffer_minutes: int = Field(ge=0)
    walk_meters: int = Field(ge=0)
    evidence_state: Literal["VERIFIED_SNAPSHOT", "USER_ESTIMATE"]


class Decision(StrictModel):
    action: Literal["approve", "edit", "reject", "cancel"]
    proposal_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    revision: int = Field(ge=1)
    new_budget_cents: int | None = Field(default=None, ge=5000, le=1000000, strict=True)

    @model_validator(mode="after")
    def edit_has_value(self):
        if self.action == "edit" and self.new_budget_cents is None:
            raise ValueError("An edit requires a new per-person budget")
        if self.action != "edit" and self.new_budget_cents is not None:
            raise ValueError("Only edits may change budget")
        return self


class NoteInput(StrictModel):
    note: str = Field(min_length=1, max_length=2000)


class LoginInput(StrictModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=12, max_length=200)


class RunOptions(StrictModel):
    simulate_cloud_429: bool = False
    repair_enabled: bool = True


class PlanChoice(StrictModel):
    lodging_tier: Literal["standard", "economy"] = "standard"
    activities_per_day: Literal[1, 2] = 2
    activities: dict[str, list[str]]
    explanation: str = Field(max_length=1800)
    expected_cost_cents: int | None = Field(
        default=None, ge=0, description="Expected GROUP total in integer USD cents, including contingency"
    )


class RepairSelection(StrictModel):
    candidate_index: int = Field(ge=0, le=2)
    explanation: str = Field(max_length=1200)


class QueryRewrite(StrictModel):
    query: str = Field(min_length=3, max_length=300)
    reason: str = Field(max_length=500)


class SpecialistResult(StrictModel):
    option_ids: list[str] = Field(max_length=15)
    observation: str = Field(max_length=1000)


class ModelPreferences(Preferences):
    @field_validator("preferred_categories")
    @classmethod
    def unique_categories(cls, value):
        return sorted(set(value))
