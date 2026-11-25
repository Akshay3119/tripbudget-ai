import secrets

import httpx
import pytest

from tripbudget.api import create_app
from tripbudget.errors import DomainError
from tripbudget.evidence import Catalog
from tripbudget.persistence import Store
from tripbudget.schemas import ModelPreferences, PlanChoice, QueryRewrite, SpecialistResult
from tripbudget.settings import Settings


@pytest.fixture
def settings():
    return Settings(enable_test_controls=True)


@pytest.fixture
def catalog(settings):
    return Catalog(settings.corpus_dir / "catalog.json")


class FixtureProviders:
    """Explicit unit/integration fixture; never used in real adversarial/evaluation evidence."""

    def __init__(self, catalog, fail_private=False):
        self.catalog = catalog
        self.fail_private = fail_private

    async def complete(self, task, schema, payload, budget, **kwargs):
        if task == "preference_parse":
            if self.fail_private:
                raise DomainError("LOCAL_UNAVAILABLE", "Local fixture unavailable", 503)
            return ModelPreferences(diet="vegetarian", maximum_walk_meters=6000)
        if schema is QueryRewrite:
            return QueryRewrite(query="NYC opening hours admission", reason="Fixture query")
        if issubclass(schema, PlanChoice):
            cities = payload["constraints"]["cities"]
            return PlanChoice(
                lodging_tier="economy",
                activities_per_day=1,
                activities={
                    city: [x["id"] for x in self.catalog.activities.values() if x["city"] == city]
                    for city in cities
                },
                explanation="Explicit integration test fixture",
            )
        return SpecialistResult(option_ids=[], observation="Fixture observation, not a real model result")


class FixtureCorpus:
    async def retrieve_and_refine(self, request, providers, budget):
        await budget.store.event(budget.episode, "fixture_retrieval", {"is_test_fixture": True})
        return {"chunks": [], "rounds": []}


@pytest.fixture
async def service(settings, catalog):
    store = Store(settings)
    uid = "test-" + secrets.token_hex(8)
    await store.execute(
        "INSERT INTO app_users(uid,username,password_hash,role) VALUES(%s,%s,%s,'evaluation')",
        (uid, uid, "not-a-login-hash"),
    )
    token = await store.new_session(uid)
    app = create_app(settings, corpus=FixtureCorpus(), providers=FixtureProviders(catalog))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer " + token},
        ) as client:
            yield app, client, uid
