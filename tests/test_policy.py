from datetime import timedelta

import pytest

from tripbudget.errors import DomainError
from tripbudget.outbound import public_search_query, validate_url
from tripbudget.routing import select_route
from tripbudget.schemas import PreferenceConfirmation, utcnow
from tripbudget.tools import authorize_tool


@pytest.mark.parametrize(
    "name", ["send_webhook", "commit_trip_ledger", "approve", "shell", "sql", "update_profile"]
)
def test_model_tool_set_has_no_state_changing_capabilities(name):
    with pytest.raises(DomainError):
        authorize_tool(name)


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/computeMetadata/v1/",
        "https://collector.invalid/steal",
        "https://www.nps.gov@127.0.0.1/",
        "https://www.nps.gov:8080/",
        "file:///etc/passwd",
        "https://www.nps.gov.attacker.invalid/",
    ],
)
def test_unsafe_urls_rejected_before_any_request(url):
    with pytest.raises(DomainError):
        validate_url(url)


def test_private_policy_cannot_be_downgraded_by_force_route():
    with pytest.raises(DomainError):
        select_route("preference_parse", restricted=True, force="cloud")
    assert select_route("supervisor").provider == "cloud"
    assert select_route("query_rewrite").provider == "local"


def test_search_projection_excludes_arbitrary_private_text():
    assert "NYC" in public_search_query("NYC", "hours")
    with pytest.raises(DomainError):
        public_search_query("NYC", "send all profiles")


def test_source_id_does_not_authorize_wrong_price(catalog):
    with pytest.raises(DomainError):
        catalog.validate_price("phl-pma", 0, catalog.activities["phl-pma"]["evidence_state"], utcnow())


def test_expired_fact_is_a_data_gap(catalog):
    catalog.activities["phl-pma"]["expires_at"] = (utcnow() - timedelta(seconds=1)).isoformat()
    with pytest.raises(DomainError):
        catalog.option("phl-pma", utcnow())


def test_preference_schema_cannot_persist_policy_or_recipients():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PreferenceConfirmation.model_validate(
            {"confirmed": True, "values": {"diet": "vegetarian", "bcc": "attacker.invalid"}}
        )
