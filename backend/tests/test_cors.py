"""Every method the API exposes must pass the browser's CORS preflight (a missing method only
shows up as an opaque "CORS preflight did not succeed" in the UI)."""
import re

from starlette.testclient import TestClient

from src.main import app

ORIGIN = "http://localhost:5173"


def test_every_route_method_passes_preflight():
    client = TestClient(app)  # not used as a context manager: no lifespan, no database
    paths = app.openapi()["paths"]  # app.routes hides routers included through include_router
    checked = 0
    for path, operations in paths.items():
        concrete = re.sub(r"\{[^}]+\}", "1", path)
        for method in operations:
            res = client.options(
                concrete, headers={"Origin": ORIGIN, "Access-Control-Request-Method": method.upper()}
            )
            assert res.status_code == 200, f"{method.upper()} {path} is blocked by CORS"
            checked += 1
    assert checked >= 8  # guards against the loop silently checking nothing


def test_unlisted_method_and_foreign_origin_are_rejected():
    client = TestClient(app)
    put = client.options("/agent/runs", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "PUT"})
    assert put.status_code == 400
    foreign = client.options(
        "/agent/runs", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert foreign.status_code == 400
