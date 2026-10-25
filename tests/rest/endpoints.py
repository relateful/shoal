from shoal.payloads.api import DOCS_BASE_URL
from shoal.rest import endpoints


def test_every_declared_endpoint_links_to_its_docs_section() -> None:
    names = {name for name in dir(endpoints) if name.isupper() and name != "ALL_ROUTES"}
    declared = {getattr(endpoints, name) for name in names}
    assert declared == set(endpoints.ALL_ROUTES)
    for route in endpoints.ALL_ROUTES:
        assert route.docs.startswith(DOCS_BASE_URL)
        assert "#" in route.docs


def test_interaction_routes_skip_the_global_rate_limit() -> None:
    interaction_routes = [route for route in endpoints.ALL_ROUTES if "interaction_token" in route.parameters]
    assert len(interaction_routes) == 8
    assert not any(route.global_limit for route in interaction_routes)
    assert all(route.global_limit for route in endpoints.ALL_ROUTES if route not in interaction_routes)
