import ast
from pathlib import Path

from app.integrations.core import IntegrationCapability, IntegrationRegistry
from app.integrations.providers.shopify.catalog import ShopifyProductCatalogAdapter
from app.integrations.registry import build_integration_registry

BACKEND = Path(__file__).parents[1] / "app"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_application_services_and_integrations_do_not_depend_on_api_routes():
    forbidden_prefix = "app.api.routes"
    files = [
        *BACKEND.joinpath("services").rglob("*.py"),
        *BACKEND.joinpath("integrations").rglob("*.py"),
    ]

    violations = {
        str(path.relative_to(BACKEND)): sorted(
            module
            for module in _imports(path)
            if module == forbidden_prefix or module.startswith(f"{forbidden_prefix}.")
        )
        for path in files
    }

    assert {name: imports for name, imports in violations.items() if imports} == {}


def test_non_shopify_routes_do_not_import_shopify_route_business_logic():
    integration_route = "app.api.routes.integrations"
    route_files = [
        path
        for path in BACKEND.joinpath("api/routes").glob("*.py")
        if path.name != "integrations.py"
    ]

    violations = [str(path.name) for path in route_files if integration_route in _imports(path)]

    assert violations == []


def test_feature_modules_do_not_depend_on_legacy_route_modules():
    legacy_routes = "app.api.routes"
    feature_files = BACKEND.joinpath("features").rglob("*.py")
    violations = {
        str(path.relative_to(BACKEND)): sorted(
            module
            for module in _imports(path)
            if module == legacy_routes or module.startswith(f"{legacy_routes}.")
        )
        for path in feature_files
    }

    assert {name: imports for name, imports in violations.items() if imports} == {}


def test_legacy_route_imports_reexport_feature_routers():
    from app.api.routes.auth import router as legacy_auth_router
    from app.api.routes.customers import router as legacy_customers_router
    from app.api.routes.inbox import router as legacy_inbox_router
    from app.api.routes.tickets import router as legacy_tickets_router
    from app.features.auth.router import router as auth_router
    from app.features.customers.router import router as customers_router
    from app.features.inbox.router import router as inbox_router
    from app.features.tickets.router import router as tickets_router

    assert legacy_auth_router is auth_router
    assert legacy_customers_router is customers_router
    assert legacy_inbox_router is inbox_router
    assert legacy_tickets_router is tickets_router


def test_default_provider_registration_is_centralized_and_resolves_shopify_capabilities():
    registry = build_integration_registry()

    assert isinstance(registry, IntegrationRegistry)
    descriptors = registry.list_providers()
    assert [descriptor.provider_id for descriptor in descriptors] == ["shopify"]
    adapter = registry.get_capability(
        "shopify", IntegrationCapability.PRODUCT_CATALOG, ShopifyProductCatalogAdapter
    )
    assert isinstance(adapter, ShopifyProductCatalogAdapter)
    from app.integrations.core.interfaces import CommerceCapability

    commerce = registry.get_capability(
        "shopify", IntegrationCapability.COMMERCE, CommerceCapability
    )
    assert isinstance(commerce, CommerceCapability)
