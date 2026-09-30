import pytest

from app import create_app
from tests.test_app import _csrf


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "t.db"),
        "UPLOAD_FOLDER": str(tmp_path / "up"),
    })
    (tmp_path / "up").mkdir(exist_ok=True)
    yield app


@pytest.fixture
def client(app):
    c = app.test_client()
    c.get("/setup")
    c.post("/setup", data=_csrf(c, "/setup") | {
        "nome": "Dinda", "email": "dinda@ex.com", "senha": "segredo1", "empresa": "Construtora X"})
    return c


