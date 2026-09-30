import io
import sqlite3

from app import create_app
from app.models import Documento, Lancamento, NotaFiscal, Venda
from tests.test_app import post


def _id(resp):
    return int(resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1])


def test_documentos_em_todas_as_areas(app, client):
    obra = _id(post(client, "/obras/nova", {"nome": "Ed. Sol", "status": "Em andamento"}))
    cli = _id(post(client, "/clientes/novo", {"nome": "Ana", "cpf_cnpj": "123"}))
    forn = _id(post(client, "/fornecedores/novo", {"nome": "Depósito X Ltda", "ativo": "1"}))
    venda = _id(post(client, "/vendas/nova", {"cliente_id": cli, "obra_id": obra, "unidade": "Apto 101",
                                             "valor": "300.000,00", "status": "Contrato assinado"}))
    for entidade, eid, voltar in [("empresa", "", "/empresa"), ("obra", obra, f"/obras/{obra}"),
                                  ("cliente", cli, f"/clientes/{cli}"), ("venda", venda, f"/vendas/{venda}"),
                                  ("fornecedor", forn, f"/fornecedores/{forn}"), ("juridico", "", "/juridico")]:
        r = post(client, "/documentos/novo", {
            "entidade": entidade, "entidade_id": eid, "voltar": voltar, "categoria": "Outros",
            "validade": "2020-01-01",
            "arquivos": [(io.BytesIO(b"a"), "Contrato São José.pdf"), (io.BytesIO(b"b"), "foto.jpg")],
        }, content_type="multipart/form-data")
        assert r.headers["Location"] == voltar
        html = client.get(voltar).get_data(as_text=True)
        assert "Contrato São José" in html and "foto" in html, entidade
    with app.app_context():
        assert Documento.query.count() == 12
        doc = Documento.query.first()
        doc_id, arquivo = doc.id, doc.arquivo
    # Download mantém o conteúdo
    assert client.get(f"/arquivo/{arquivo}").data == b"a"
    # Busca geral e vencidos no painel
    assert "Contrato São José" in client.get("/documentos?busca=José").get_data(as_text=True)
    assert "vencido" in client.get("/").get_data(as_text=True)
    # Editar e excluir
    assert client.get(f"/documentos/{doc_id}/editar").status_code == 200
    post(client, f"/documentos/{doc_id}/editar", {"titulo": "Cartão CNPJ", "categoria": "Cartão CNPJ"})
    post(client, f"/documentos/{doc_id}/excluir", {})
    with app.app_context():
        assert Documento.query.count() == 11
    # Arquivo proibido é recusado sem gravar nada
    r = post(client, "/documentos/novo", {"entidade": "juridico", "voltar": "/juridico",
                                          "arquivos": [(io.BytesIO(b"x"), "a.exe")]},
             content_type="multipart/form-data", follow_redirects=True)
    assert "não permitido" in r.get_data(as_text=True)


def test_venda_com_recebimentos(app, client):
    cli = _id(post(client, "/clientes/novo", {"nome": "Bruno"}))
    venda = _id(post(client, "/vendas/nova", {"cliente_id": cli, "unidade": "Casa 2", "valor": "100000"}))
    form = client.get(f"/financeiro/novo?venda={venda}").get_data(as_text=True)
    assert "Recebimento Casa 2" in form
    post(client, "/financeiro/novo", {"tipo": "entrada", "descricao": "Entrada", "valor": "30.000,00",
                                      "data": "2026-09-01", "venda_id": venda})
    with app.app_context():
        v = db_get(Venda, venda)
        assert str(v.recebido) == "30000" and str(v.a_receber) == "70000"
        assert Lancamento.query.one().cliente_id == cli
    html = client.get(f"/vendas/{venda}").get_data(as_text=True)
    assert "R$ 70.000,00" in html
    for url in ["/vendas", "/clientes", f"/clientes/{cli}", f"/financeiro?cliente={cli}"]:
        assert client.get(url).status_code == 200, url
    # Venda com recebimento não pode ser excluída
    post(client, f"/vendas/{venda}/excluir", {})
    with app.app_context():
        assert Venda.query.count() == 1


def test_fornecedor_nota_e_pagamento(app, client):
    forn = _id(post(client, "/fornecedores/novo", {"nome": "Cimentos SA", "cpf_cnpj": "00.000/0001-00", "ativo": "1"}))
    post(client, "/notas/nova", {"tipo": "entrada", "numero": "55", "valor": "1.000,00", "data_emissao": "2026-09-02",
                                 "fornecedor_id": forn, "gerar_lancamento": "1"})
    post(client, "/financeiro/novo", {"tipo": "saida", "descricao": "Frete", "valor": "200",
                                      "data": "2026-09-03", "fornecedor_id": forn})
    with app.app_context():
        nota = NotaFiscal.query.one()
        assert nota.parceiro == "Cimentos SA" and nota.lancamento.fornecedor_id == forn
    html = client.get(f"/fornecedores/{forn}").get_data(as_text=True)
    assert "R$ 1.200,00" in html
    assert "R$ 1.200,00" in client.get("/fornecedores").get_data(as_text=True)
    csv = client.get(f"/financeiro/exportar.csv?fornecedor={forn}").get_data(as_text=True)
    assert "Cimentos SA" in csv and "Frete" in csv


def test_banco_antigo_e_atualizado(tmp_path):
    db_path = tmp_path / "antigo.db"
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE lancamento (id INTEGER PRIMARY KEY, tipo VARCHAR(10) NOT NULL, descricao VARCHAR(255) NOT NULL,
          categoria VARCHAR(80), data DATE NOT NULL, forma_pagamento VARCHAR(40), obra_id INTEGER, nota_id INTEGER,
          pagamento_id INTEGER, criado_em DATETIME, valor_centavos INTEGER NOT NULL, arquivo VARCHAR(255),
          arquivo_nome VARCHAR(255));
        INSERT INTO lancamento (tipo, descricao, data, valor_centavos) VALUES ('saida', 'Antigo', '2026-01-01', 500);
    """)
    con.close()
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}", "UPLOAD_FOLDER": str(tmp_path / "up")})
    with app.app_context():
        l = Lancamento.query.one()
        assert l.descricao == "Antigo" and l.fornecedor_id is None


def db_get(modelo, id):
    from app.models import db
    return db.session.get(modelo, id)
