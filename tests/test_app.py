import io
import re
from datetime import date

import pytest

from app import create_app
from app.models import Lancamento, NotaFiscal, PagamentoFuncionario
from app.utils import formata_moeda, parse_valor


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


def _csrf(client, url):
    html = client.get(url).get_data(as_text=True)
    m = re.search(r'name="_csrf" value="([^"]+)"', html)
    return {"_csrf": m.group(1)} if m else {}


def post(client, url, data, **kw):
    r = client.post(url, data=_csrf(client, "/empresa") | data, **kw)
    assert r.status_code in (200, 302), (url, r.status_code)
    return r


def test_parse_e_formata_valor():
    assert str(parse_valor("R$ 1.234,56")) == "1234.56"
    assert str(parse_valor("1234.5")) == "1234.50"
    assert formata_moeda(parse_valor("1234567,8")) == "R$ 1.234.567,80"
    assert formata_moeda(-5) == "-R$ 5,00"


def test_redireciona_para_setup_sem_usuario(app):
    c = app.test_client()
    assert c.get("/").headers["Location"].endswith("/setup")


def test_login_obrigatorio(app, client):
    anon = app.test_client()
    assert "/login" in anon.get("/financeiro").headers["Location"]


def test_post_sem_csrf_rejeitado(client):
    r = client.post("/obras/nova", data={"nome": "X", "_csrf": "errado"})
    assert r.status_code == 400


def test_fluxo_completo(app, client):
    # Obra
    r = post(client, "/obras/nova", {"nome": "Casa Azul", "orcamento": "100.000,00", "status": "Em andamento"})
    assert r.status_code == 302
    obra_id = int(r.headers["Location"].rsplit("/", 1)[-1])

    # Entrada manual com anexo
    r = post(client, "/financeiro/novo", {
        "tipo": "entrada", "descricao": "Medição 1", "valor": "30.000,00", "data": "2026-09-10",
        "categoria": "Medição / Recebimento de cliente", "obra_id": obra_id,
        "arquivo": (io.BytesIO(b"%PDF-1.4"), "recibo.pdf"),
    }, content_type="multipart/form-data")
    assert r.status_code == 302

    # Nota fiscal recebida gera saída
    post(client, "/notas/nova", {
        "tipo": "entrada", "numero": "123", "valor": "5.000,00", "data_emissao": "2026-09-11",
        "parceiro": "Depósito", "obra_id": obra_id, "gerar_lancamento": "1",
        "categoria": "Material de construção", "arquivo": (io.BytesIO(b"<xml/>"), "nf.xml"),
    }, content_type="multipart/form-data")

    # Contrato
    post(client, "/contratos/novo", {"titulo": "Empreitada", "valor": "100000", "data_fim": date.today().isoformat(),
                                     "status": "Vigente", "obra_id": obra_id})

    # Funcionário + pagamento gera saída
    r = post(client, "/funcionarios/novo", {"nome": "João", "salario": "2.500,00", "ativo": "1", "obra_id": obra_id})
    func_id = int(r.headers["Location"].rsplit("/", 1)[-1])
    post(client, "/pagamentos/novo", {"funcionario_id": func_id, "tipo": "Salário", "valor": "2.500,00",
                                      "data_pagamento": "2026-09-05", "competencia": "2026-08",
                                      "forma_pagamento": "PIX", "obra_id": obra_id})

    with app.app_context():
        lancs = Lancamento.query.filter_by(obra_id=obra_id).all()
        assert sorted((l.tipo, l.valor_centavos) for l in lancs) == [
            ("entrada", 3_000_000), ("saida", 250_000), ("saida", 500_000)]
        nota = NotaFiscal.query.one()
        assert nota.lancamento.tipo == "saida" and nota.arquivo

    # Páginas renderizam
    for url in ["/", "/obras", f"/obras/{obra_id}", "/financeiro", "/notas", "/contratos",
                "/funcionarios", f"/funcionarios/{func_id}", "/pagamentos", "/relatorios",
                "/empresa", "/usuarios", "/financeiro/exportar.csv?obra=" + str(obra_id),
                "/financeiro/novo", "/notas/nova", "/contratos/novo", "/pagamentos/novo"]:
        assert client.get(url).status_code == 200, url

    html = client.get(f"/obras/{obra_id}").get_data(as_text=True)
    assert "R$ 22.500,00" in html  # saldo: 30.000 - 5.000 - 2.500
    csv = client.get("/financeiro/exportar.csv").get_data(as_text=True)
    assert "Medição 1" in csv and "-2500,00" in csv

    # Download de anexo
    with app.app_context():
        nome = NotaFiscal.query.one().arquivo
    assert client.get(f"/arquivo/{nome}").data == b"<xml/>"

    # Desmarcar "lançar no financeiro" remove o lançamento
    with app.app_context():
        nota_id = NotaFiscal.query.one().id
    post(client, f"/notas/{nota_id}/editar", {"tipo": "entrada", "numero": "123", "valor": "5000",
                                              "data_emissao": "2026-09-11"})
    with app.app_context():
        assert NotaFiscal.query.one().lancamento is None
        assert Lancamento.query.count() == 2

    # Excluir pagamento remove a saída
    with app.app_context():
        pag_id = PagamentoFuncionario.query.one().id
    post(client, f"/pagamentos/{pag_id}/excluir", {})
    with app.app_context():
        assert Lancamento.query.count() == 1

    # Obra com vínculos não pode ser excluída
    r = post(client, f"/obras/{obra_id}/excluir", {}, follow_redirects=True)
    assert "vinculados" in r.get_data(as_text=True)
    assert client.get(f"/obras/{obra_id}").status_code == 200


def test_erro_de_validacao_mantem_dados(client):
    r = post(client, "/financeiro/novo", {"tipo": "saida", "descricao": "Areia", "valor": "abc", "data": "2026-09-01"})
    assert r.status_code == 200
    assert "Valor inválido" in r.get_data(as_text=True)
    assert 'value="Areia"' in r.get_data(as_text=True)


def test_anexo_extensao_proibida(client):
    r = post(client, "/financeiro/novo", {
        "tipo": "saida", "descricao": "X", "valor": "10", "data": "2026-09-01",
        "arquivo": (io.BytesIO(b"x"), "virus.exe")}, content_type="multipart/form-data")
    assert "não permitido" in r.get_data(as_text=True)


def test_redirect_externo_bloqueado(client):
    r = post(client, "/financeiro/novo?voltar=https://mal.com", {
        "tipo": "saida", "descricao": "X", "valor": "10", "data": "2026-09-01"})
    assert r.headers["Location"] == "/financeiro"
