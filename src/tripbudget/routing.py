from dataclasses import dataclass

from .errors import DomainError


@dataclass(frozen=True)
class Route:
    provider: str
    reason: str


def select_route(task: str, restricted=False, force=None) -> Route:
    if restricted:
        if force and force != "local":
            raise DomainError("PRIVACY_POLICY", "Restricted input is local-only", 403)
        return Route("local", "restricted_input_no_external_model")
    if force:
        if force not in {"cloud", "local"}:
            raise ValueError("Invalid provider")
        return Route(force, "matched_provider_evaluation")
    if task in {"query_rewrite", "relevance_grade", "preference_parse"}:
        return Route("local", "short_structured_utility")
    return Route("cloud", "public_multistep_planning")
