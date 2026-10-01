import io
import re
import time
import zipfile

from app import create_app
from app.backup import gerar_backup, limpar_antigos
from app.models import Atividade, Usuario, db
from app.seguranca import _codigo_totp, validar_senha
from tests.test_app import _csrf, post


def _login(c, email="dinda@ex.com", senha="segredo-forte-1"):
    return c.post("/login", data=_csrf(c, "/login") | {"email": email, "senha": senha})


def test_politica_de_senha():
    assert validar_senha("curta1") is not None
    assert validar_senha("somenteletras") is not None
    assert validar_senha("1234567890") is not None
    assert validar_senha("obra-azul-2026") is None


def test_bloqueio_apos_tentativas_erradas(app, client):
    client.post("/logout", data=_csrf(client, "/"))
    for _ in range(5):
        r = _login(client, senha="errada-123")
        assert r.status_code == 200
    # Mesmo com a senha certa, fica bloqueado
    r = _login(client)
    assert r.status_code == 429 and "aguarde 15 minutos" in r.get_data(as_text=True)


def test_verificacao_em_duas_etapas(app, client):
    html = client.get("/seguranca").get_data(as_text=True)
    assert "<svg" in html
    segredo = re.search(r'user-select-all"[^>]*>([A-Z2-7]+)<', html).group(1)
    agora = int(time.time()) // 30
    post(client, "/seguranca", {"acao": "ativar", "codigo": _codigo_totp(segredo, agora)})
    with app.app_context():
        assert db.session.get(Usuario, 1).totp_ativo
    client.post("/logout", data=_csrf(client, "/"))
    # Senha certa leva para a tela do código; sem o código não entra
    r = _login(client)
    assert r.headers["Location"].endswith("/login/codigo")
    assert "/login" in client.get("/financeiro").headers["Location"]
    # Código já usado na ativação não pode ser reutilizado
    r = client.post("/login/codigo", data=_csrf(client, "/login/codigo") | {"codigo": _codigo_totp(segredo, agora)})
    assert r.status_code == 200 and "incorreto" in r.get_data(as_text=True)
    r = client.post("/login/codigo", data=_csrf(client, "/login/codigo") | {"codigo": _codigo_totp(segredo, agora + 1)})
    assert r.status_code == 302
    assert client.get("/financeiro").status_code == 200


def test_setup_exige_codigo_de_instalacao(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/s.db", "UPLOAD_FOLDER": str(tmp_path / "u"),
                      "SETUP_TOKEN": "abc-123"})
    c = app.test_client()
    dados = {"nome": "X", "email": "x@x.com", "senha": "segredo-forte-1", "senha2": "segredo-forte-1"}
    r = c.post("/setup", data=_csrf(c, "/setup") | dados | {"token": "errado"})
    assert "incorreto" in r.get_data(as_text=True)
    r = c.post("/setup", data=_csrf(c, "/setup") | dados | {"token": "abc-123"})
    assert r.status_code == 302
    with app.app_context():
        assert Usuario.query.count() == 1


def test_sessao_expira_por_inatividade(app, client):
    assert client.get("/").status_code == 200
    with client.session_transaction() as s:
        s["ultimo_acesso"] = int(time.time()) - 2 * 3600
    r = client.get("/financeiro")
    assert "/login" in r.headers["Location"]


def test_cabecalhos_de_seguranca(client):
    r = client.get("/")
    assert "script-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "<script>" not in r.get_data(as_text=True)  # nenhum script embutido (CSP bloquearia)


def test_cookies_seguros_em_producao(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/p.db", "UPLOAD_FOLDER": str(tmp_path / "u"),
                      "PRODUCAO": True})
    assert app.config["SESSION_COOKIE_SECURE"] is True and app.config["SESSION_COOKIE_HTTPONLY"] is True
    r = app.test_client().get("/setup", headers={"X-Forwarded-Proto": "https"})
    assert "max-age" in r.headers["Strict-Transport-Security"]


def test_registro_de_atividades(app, client):
    post(client, "/obras/nova", {"nome": "Obra Log", "status": "Em andamento"})
    post(client, "/obras/1/excluir", {})
    with app.app_context():
        acoes = [a.acao for a in Atividade.query.order_by(Atividade.id).all()]
    assert "Entrou no sistema" in acoes and "Criou obra" in acoes and "Excluiu obra" in acoes
    assert "Criou obra" in client.get("/atividades").get_data(as_text=True)


def test_backup_completo(app, client, tmp_path):
    post(client, "/documentos/novo", {"entidade": "empresa", "voltar": "/empresa",
                                      "arquivos": [(io.BytesIO(b"cnpj"), "cnpj.pdf")]},
         content_type="multipart/form-data")
    r = client.post("/backup/baixar", data=_csrf(client, "/backup"))
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.data))
    nomes = z.namelist()
    assert "instance/construtora.db" in nomes
    assert any(n.startswith("instance/uploads/") and z.read(n) == b"cnpj" for n in nomes)
    # Backup agendado (linha de comando) + limpeza dos antigos
    arq = gerar_backup(app, str(tmp_path / "bk"))
    assert zipfile.is_zipfile(arq)
    limpar_antigos(str(tmp_path / "bk"), 30)
    assert (tmp_path / "bk").exists() and len(list((tmp_path / "bk").iterdir())) == 1
