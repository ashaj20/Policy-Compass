from fastapi import APIRouter
from pydantic import BaseModel, field_validator
from sqlalchemy import text

from app.errors import PermissionDenied


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_pgvector_available(db):
    assert db.execute(text("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector")).scalar() == 1.0


def test_unknown_route_returns_friendly_404(client):
    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"]["message"] == "This page or item could not be found."


def _add_test_routes(app):
    router = APIRouter()

    class Payload(BaseModel):
        name: str

        @field_validator("name")
        @classmethod
        def not_blank(cls, v: str) -> str:
            if not v.strip():
                raise ValueError("Name is required")
            return v

    @router.get("/boom")
    def boom():
        raise RuntimeError("secret internal detail")

    @router.get("/forbidden")
    def forbidden():
        raise PermissionDenied("You don't have permission to view this policy.")

    @router.post("/validate")
    def validate(payload: Payload):
        return payload

    app.include_router(router, prefix="/api/_test")


def test_unexpected_error_hides_details_and_returns_error_id(app, client):
    _add_test_routes(app)
    resp = client.get("/api/_test/boom")
    assert resp.status_code == 500
    body = resp.json()["error"]
    assert body["message"] == "Something went wrong. Please try again."
    assert len(body["error_id"]) == 12
    assert "secret" not in resp.text and "Traceback" not in resp.text


def test_permission_error_message(app, client):
    _add_test_routes(app)
    resp = client.get("/api/_test/forbidden")
    assert resp.status_code == 403
    assert resp.json()["error"] == {
        "code": "permission_denied",
        "message": "You don't have permission to view this policy.",
    }


def test_validation_errors_are_reported_per_field(app, client):
    _add_test_routes(app)
    resp = client.post("/api/_test/validate", json={"name": "  "})
    assert resp.status_code == 422
    assert resp.json()["error"]["fields"] == {"name": "Name is required"}
