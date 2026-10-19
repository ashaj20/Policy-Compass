"""Only public pages may be shown in another site's frame (US-030); the internal app and the
API refuse, protecting signed-in staff from clickjacking (US-037)."""

from fastapi.testclient import TestClient

from app.frontend import mount_frontend
from app.main import create_app


def frontend_client(tmp_path):
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "widget.js").write_text("(function(){})()")
    app = create_app()
    mount_frontend(app, str(tmp_path))
    return TestClient(app)


def test_public_pages_and_the_widget_can_be_embedded(tmp_path):
    client = frontend_client(tmp_path)
    for path in ("/p/riverside-housing", "/p/riverside-housing/widget"):
        resp = client.get(path)
        assert resp.headers["content-security-policy"] == "frame-ancestors *"
        assert "x-frame-options" not in resp.headers


def test_the_internal_app_and_api_refuse_to_be_framed(tmp_path):
    client = frontend_client(tmp_path)
    for path in ("/", "/internal", "/internal/settings/members", "/login", "/api/health"):
        resp = client.get(path)
        assert resp.headers["x-frame-options"] == "DENY", path
        assert resp.headers["content-security-policy"] == "frame-ancestors 'none'", path
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_existing_content_security_policies_are_kept_and_extended(make_client, storage):
    from tests.test_organisation_settings import PNG

    jane = make_client("jane@example.org")
    org_id = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    ).json()["id"]
    jane.put(f"/api/organisations/{org_id}/logo", files={"file": ("logo.png", PNG, "image/png")})
    resp = jane.get("/api/public/organisations/riverside-housing/logo")
    assert resp.status_code == 200
    assert resp.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
