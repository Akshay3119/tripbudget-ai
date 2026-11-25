"""Explicit HTTP model fixtures: provider regression tests, never real-run evaluation evidence."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from jsonschema.exceptions import ValidationError as JsonSchemaError
from pydantic import SecretStr

from tripbudget.errors import DomainError
from tripbudget.providers import Providers, output_contract, validate_output
from tripbudget.schemas import PlanChoice, QueryRewrite
from tripbudget.settings import Settings


class FixtureBudget:
    def __init__(self, episode="fixture", remaining=10):
        self.episode = episode
        self.events = []
        self.reservations = []
        self.settlements = []
        self.store = SimpleNamespace(event=self.event)
        self.remaining = remaining

    async def event(self, episode, kind, data):
        self.events.append((kind, data))

    async def reserve(self, *args, **kwargs):
        self.reservations.append((args, kwargs))
        return str(len(self.reservations))

    async def settle(self, *args):
        self.settlements.append(args)

    async def remaining_seconds(self):
        return self.remaining


def fixture_settings(**changes):
    return Settings(nvidia_api_key=SecretStr("unit-fixture-token")).model_copy(update=changes)


def test_wire_contract_requires_explicit_default_fields_without_mutating_application_schema():
    original = PlanChoice.model_json_schema()
    wire = output_contract(PlanChoice)
    assert set(wire["required"]) == set(wire["properties"])
    assert "default" not in wire["properties"]["lodging_tier"]
    assert original == PlanChoice.model_json_schema()
    assert original["properties"]["lodging_tier"]["default"] == "standard"
    with pytest.raises(JsonSchemaError):
        validate_output('{"activities":{},"explanation":"not a complete answer"}', PlanChoice, wire, "stop")


def test_truncated_even_parseable_output_is_rejected():
    with pytest.raises(DomainError, match="output limit"):
        validate_output(
            '{"query":"NYC prices hours","reason":"test"}',
            QueryRewrite,
            output_contract(QueryRewrite),
            "length",
        )


async def test_cloud_429_uses_real_provider_path_to_gguf_and_validates_same_contract():
    requests = []

    async def handler(request):
        requests.append((str(request.url), json.loads(request.content)))
        if request.url.path.endswith("/chat/completions"):
            native = requests[-1][1]["response_format"]
            assert native["type"] == "json_schema" and native["json_schema"]["strict"] is True
            assert native["json_schema"]["schema"] == output_contract(QueryRewrite)
            return httpx.Response(429)
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"format": "gguf"}})
        body = requests[-1][1]
        assert body["format"] == output_contract(QueryRewrite)
        assert body["think"] is False and body["options"]["num_ctx"] == 8192
        return httpx.Response(
            200,
            json={
                "message": {"content": '{"query":"NYC admission hours","reason":"fixture"}'},
                "done_reason": "stop",
                "prompt_eval_count": 40,
                "eval_count": 12,
            },
        )

    budget = FixtureBudget()
    result = await Providers(fixture_settings(), httpx.MockTransport(handler)).complete(
        "supervisor", QueryRewrite, {"instruction": "fixture"}, budget
    )
    assert result.query == "NYC admission hours"
    assert len(budget.reservations) == 2 and budget.reservations[1][1]["logical"] is False
    assert budget.settlements[0][-1] == "HTTP_429"
    assert budget.settlements[-1][1:3] == (40, 12)
    assert budget.events[-1][1]["local_backend"]["format"] == "gguf"
    assert [u.split("/")[-1] for u, _ in requests] == ["completions", "show", "chat"]


async def test_mlx_backend_cannot_receive_private_prompt_or_fall_back_to_cloud():
    requests = []

    async def handler(request):
        requests.append((str(request.url), request.content))
        return httpx.Response(200, json={"details": {"format": "safetensors", "runner": "mlx"}})

    budget = FixtureBudget(episode=None)
    with pytest.raises(DomainError, match="LOCAL_BACKEND_UNSUPPORTED"):
        await Providers(fixture_settings(), httpx.MockTransport(handler)).complete(
            "preference_parse",
            QueryRewrite,
            {"untrusted_note": "PRIVATE_UNIT_CANARY"},
            budget,
            restricted=True,
        )
    assert len(requests) == 1 and requests[0][0].endswith("/api/show")
    assert b"PRIVATE_UNIT_CANARY" not in requests[0][1]
    assert len(budget.reservations) == 1


async def test_gguf_preflight_is_cached_and_missing_default_field_is_not_silently_filled():
    shows = []

    async def handler(request):
        if request.url.path == "/api/show":
            shows.append(1)
            return httpx.Response(200, json={"details": {"format": "gguf"}})
        return httpx.Response(
            200,
            json={
                "message": {"content": '{"activities":{},"explanation":"missing tier/cadence"}'},
                "done_reason": "stop",
                "prompt_eval_count": 20,
                "eval_count": 10,
            },
        )

    providers = Providers(fixture_settings(), httpx.MockTransport(handler))
    for _ in range(2):
        budget = FixtureBudget()
        with pytest.raises(DomainError) as error:
            await providers.complete("supervisor", PlanChoice, {}, budget, force="local")
        assert error.value.code == "PROVIDER_UNAVAILABLE"
        assert budget.settlements[-1][1:3] == (20, 10)
        assert budget.settlements[-1][-2] is False
    assert len(shows) == 1


async def test_local_queue_wait_is_included_in_attempt_deadline():
    providers = Providers(fixture_settings(), httpx.MockTransport(lambda r: httpx.Response(500)))
    budget = FixtureBudget(episode=None, remaining=0.02)
    await providers.local_gate.acquire()
    try:
        with pytest.raises(DomainError) as error:
            await asyncio.wait_for(
                providers.complete("preference_parse", QueryRewrite, {}, budget, restricted=True), timeout=0.2
            )
    finally:
        providers.local_gate.release()
    assert error.value.code == "LOCAL_UNAVAILABLE"
    assert budget.settlements[-1][-1] == "TimeoutError"


@pytest.mark.parametrize(
    "activities",
    [
        {"NYC": ["nyc-a"]},
        {"NYC": ["nyc-a", "nyc-a"]},
        {"NYC": ["nyc-a", "invented"]},
        {"Day1": ["nyc-a", "nyc-b"]},
    ],
)
def test_contextual_planning_contract_rejects_incomplete_duplicate_unknown_or_wrong_city_pool(activities):
    from tripbudget.schemas import plan_choice_schema

    schema = plan_choice_schema(["NYC"], [{"city": "NYC", "id": "nyc-a"}, {"city": "NYC", "id": "nyc-b"}])
    answer = {
        "lodging_tier": "economy",
        "activities_per_day": 1,
        "activities": activities,
        "explanation": "Fixture",
        "expected_cost_cents": None,
    }
    with pytest.raises(JsonSchemaError):
        validate_output(json.dumps(answer), schema, output_contract(schema), "stop")


def test_contextual_contract_accepts_model_rank_order_without_forcing_tier_or_cadence():
    from tripbudget.schemas import plan_choice_schema

    schema = plan_choice_schema(["NYC"], [{"city": "NYC", "id": "nyc-a"}, {"city": "NYC", "id": "nyc-b"}])
    answer = {
        "lodging_tier": "standard",
        "activities_per_day": 2,
        "activities": {"NYC": ["nyc-b", "nyc-a"]},
        "explanation": "Fixture",
        "expected_cost_cents": None,
    }
    result = validate_output(json.dumps(answer), schema, output_contract(schema), "stop")
    assert result.lodging_tier == "standard" and result.activities_per_day == 2
    assert result.activities.NYC == ["nyc-b", "nyc-a"]


def test_decoder_projection_keeps_uniqueness_enforced_in_the_full_client_contract():
    from tripbudget.providers import decoder_contract
    from tripbudget.schemas import plan_choice_schema

    schema = plan_choice_schema(["NYC"], [{"city": "NYC", "id": "nyc-a"}, {"city": "NYC", "id": "nyc-b"}])
    full = output_contract(schema)
    grammar = decoder_contract(full)
    assert "uniqueItems" not in json.dumps(grammar)
    assert "uniqueItems" in json.dumps(full)
    assert grammar["$defs"]["CityActivities"]["properties"]["NYC"]["minItems"] == 2
    bad = {
        "lodging_tier": "economy",
        "activities_per_day": 1,
        "activities": {"NYC": ["nyc-a", "nyc-a"]},
        "explanation": "Fixture",
        "expected_cost_cents": None,
    }
    with pytest.raises(JsonSchemaError):
        validate_output(json.dumps(bad), schema, full, "stop")


def test_schema_compaction_preserves_property_names_and_every_validation_constraint():
    from pydantic import BaseModel, Field
    from tripbudget.providers import prompt_contract

    class NamedFields(BaseModel):
        title: str = Field(min_length=2, description="annotation")
        description: str = Field(max_length=10)

    full = output_contract(NamedFields)
    compact = prompt_contract(full)
    assert set(compact["properties"]) == {"title", "description"}
    assert compact["required"] == ["title", "description"]
    assert compact["properties"]["title"]["minLength"] == 2
    assert compact["properties"]["description"]["maxLength"] == 10
    assert "description" not in compact["properties"]["title"]
    assert full["properties"]["title"]["description"] == "annotation"


async def test_largest_three_city_workflow_falls_back_without_context_increase_or_lost_constraints(service):
    from evaluation.scenarios import scenarios
    from tripbudget.schemas import RunOptions

    app, client, uid = service
    case = next(c for c in scenarios() if c["id"] == "F03")
    seen = []

    async def handler(request):
        body = json.loads(request.content)
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"format": "gguf"}})
        assert request.url.path == "/api/chat"
        payload = json.loads(body["messages"][1]["content"])
        assert payload["constraints"]["days"] == 7 and len(payload["constraints"]["travelers"]) == 6
        assert payload["constraints"]["cities"] == ["NYC", "PHL", "DC"]
        seen.append(body)
        properties = body["format"]["properties"]
        if "lodging_tier" in properties:
            value = {
                "lodging_tier": "economy",
                "activities_per_day": 1,
                "activities": {
                    city: [o["id"] for o in payload["catalog"] if o["city"] == city]
                    for city in payload["constraints"]["cities"]
                },
                "explanation": "Explicit HTTP fixture",
                "expected_cost_cents": None,
            }
        elif "candidate_index" in properties:
            value = {"candidate_index": 0, "explanation": "Explicit repair fixture"}
        else:
            value = {"option_ids": [], "observation": "Explicit advisory fixture"}
        return httpx.Response(
            200,
            json={
                "message": {"content": json.dumps(value)},
                "done_reason": "stop",
                "prompt_eval_count": 200,
                "eval_count": 100,
            },
        )

    app.state.workflow.providers = Providers(app.state.settings, httpx.MockTransport(handler))
    row = await app.state.store.admit(uid, case["request"], "largest-context-fixture", 300)
    result = await app.state.workflow.run(row["id"], uid, RunOptions(simulate_cloud_429=True))
    assert result["outcome"] == "PENDING_APPROVAL"
    assert seen and all(b["options"]["num_ctx"] == 8192 for b in seen)
    events = await app.state.store.all("SELECT kind,data FROM events WHERE episode=%s", (row["id"],))
    assert not any(r["kind"] == "provider_skipped" for r in events)
    assert all(
        r["data"]["input_bound"] + r["data"]["max_output"] <= 8192
        for r in events
        if r["kind"] == "model_request" and r["data"]["provider"] == "local"
    )


def test_advisory_cost_cannot_exceed_checkpoint_safe_domain_bound():
    answer = {
        "lodging_tier": "economy",
        "activities_per_day": 1,
        "activities": {"NYC": ["nyc-a"]},
        "explanation": "Fixture",
        "expected_cost_cents": 126000000000000000000,
    }
    with pytest.raises(JsonSchemaError):
        validate_output(json.dumps(answer), PlanChoice, output_contract(PlanChoice), "stop")


async def test_oversized_cloud_advisory_estimate_falls_back_before_checkpoint_and_can_commit(service):
    from evaluation.client import default_request
    from tripbudget.schemas import RunOptions, Decision, TripRequest

    app, client, uid = service
    seen = []

    async def handler(request):
        body = json.loads(request.content)
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"format": "gguf"}})
        payload = json.loads(body["messages"][1]["content"])
        is_cloud = request.url.path.endswith("/chat/completions")
        props = (
            body["response_format"]["json_schema"]["schema"]["properties"]
            if is_cloud
            else body["format"]["properties"]
        )
        if "lodging_tier" in props:
            value = {
                "lodging_tier": "economy",
                "activities_per_day": 1,
                "activities": {"NYC": [o["id"] for o in payload["catalog"]]},
                "explanation": "Explicit HTTP fixture",
                "expected_cost_cents": 126000000000000000000 if is_cloud else None,
            }
        else:
            value = {"option_ids": [], "observation": "Explicit advisory fixture"}
        seen.append((is_cloud, value))
        if is_cloud:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": json.dumps(value)}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                },
            )
        return httpx.Response(
            200,
            json={
                "message": {"content": json.dumps(value)},
                "done_reason": "stop",
                "prompt_eval_count": 100,
                "eval_count": 50,
            },
        )

    app.state.workflow.providers = Providers(fixture_settings(), httpx.MockTransport(handler))
    req = TripRequest.model_validate(default_request(days=3, cities=["NYC"])).model_dump(mode="json")
    row = await app.state.store.admit(uid, req, "oversized-advisory-fixture", 300)
    result = await app.state.workflow.run(row["id"], uid, RunOptions())
    assert (
        result["outcome"] == "PENDING_APPROVAL"
        and any(cloud for cloud, _ in seen)
        and any(not cloud for cloud, _ in seen)
    )
    approval = await app.state.store.one("SELECT * FROM approvals WHERE episode=%s", (row["id"],))
    await app.state.store.record_decision(
        uid,
        approval["id"],
        Decision(action="approve", proposal_hash=approval["hash"], revision=approval["revision"]),
        "oversized-fixture-human-approval",
    )
    committed = await app.state.workflow.run(row["id"], uid, RunOptions())
    assert committed["outcome"] == "COMMITTED"
    ledger_count = await app.state.store.one(
        "SELECT count(*) AS n FROM ledgers WHERE episode=%s", (row["id"],)
    )
    assert ledger_count["n"] == 1
    state = await app.state.store.one("SELECT payload FROM proposals WHERE episode=%s", (row["id"],))
    assert state["payload"]["choice"]["expected_cost_cents"] is None
    events = await app.state.store.all("SELECT kind,data FROM events WHERE episode=%s", (row["id"],))
    assert any(e["kind"] == "model_failure" and e["data"]["provider"] == "cloud" for e in events)
    assert not any(e["kind"] == "worker_interrupted" for e in events)


@pytest.mark.parametrize("value", [None, {}, [], 1])
def test_non_string_model_content_is_a_provider_validation_error(value):
    from tripbudget.providers import parse_json

    with pytest.raises(ValueError, match="JSON string"):
        parse_json(value)
