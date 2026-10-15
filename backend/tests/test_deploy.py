from fastapi.testclient import TestClient

from app.config import Settings
from app.frontend import mount_frontend
from app.main import create_app


def test_render_style_database_url_uses_psycopg():
    s = Settings(database_url="postgres://u:p@host:5432/db")
    assert s.database_url == "postgresql+psycopg://u:p@host:5432/db"


def test_frontend_served_with_spa_fallback_and_api_404_kept(tmp_path):
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("nope")

    app = create_app()
    mount_frontend(app, str(tmp_path))
    client = TestClient(app)

    assert client.get("/").text == "<html>app</html>"
    assert client.get("/internal/policies").text == "<html>app</html>"
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert "nope" not in client.get("/../secret.txt").text
    resp = client.get("/api/unknown")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "http_error"
