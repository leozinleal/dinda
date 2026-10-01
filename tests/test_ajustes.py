import io
import re

from app.models import Documento, Lancamento, Pedido, db
from tests.test_app import post


def _id(resp):
    return int(resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1])


def test_documentos_do_funcionario(app, client):
    f = _id(post(client, "/funcionarios/novo", {"nome": "João Pedreiro", "ativo": "1"}))
    html = client.get(f"/funcionarios/{f}").get_data(as_text=True)
    assert "Documentos do funcionário" in html and "Comprovante de residência" in html
    post(client, "/documentos/novo", {"entidade": "funcionario", "entidade_id": f, "voltar": f"/funcionarios/{f}",
                                      "categoria": "RG / CPF / CNH", "arquivos": [(io.BytesIO(b"rg"), "rg joao.pdf")]},
         content_type="multipart/form-data")
    assert "rg joao" in client.get(f"/funcionarios/{f}").get_data(as_text=True)
    assert "Funcionário: João Pedreiro" in client.get("/documentos?busca=joao").get_data(as_text=True)
    with app.app_context():
        assert Documento.query.filter_by(entidade="funcionario", entidade_id=f).count() == 1


def test_lancamento_automatico_mostra_arquivo_da_origem(app, client):
    f = _id(post(client, "/funcionarios/novo", {"nome": "Maria", "ativo": "1"}))
    post(client, "/pagamentos/novo", {"funcionario_id": f, "tipo": "Salário", "valor": "1000", "data_pagamento": "2026-09-30",
                                      "forma_pagamento": "PIX", "arquivo": (io.BytesIO(b"comprovante"), "pix.pdf")},
         content_type="multipart/form-data")
    post(client, "/notas/nova", {"tipo": "entrada", "numero": "9", "valor": "50", "data_emissao": "2026-09-30",
                                 "gerar_lancamento": "1", "arquivo": (io.BytesIO(b"nota"), "nf9.pdf")},
         content_type="multipart/form-data")
    html = client.get("/financeiro").get_data(as_text=True)
    links = re.findall(r'href="(/arquivo/[^"]+)"[^>]*title="Abrir ([^"]+)"', html)
    assert {nome for _, nome in links} == {"pix.pdf", "nf9.pdf"}
    conteudos = {client.get(url).data for url, _ in links}
    assert conteudos == {b"comprovante", b"nota"}
    with app.app_context():
        assert all(l.arquivo is None for l in Lancamento.query.all())  # arquivo continua só na origem


def test_abas_da_obra_ficam_dentro_do_tab_content(client):
    obra = _id(post(client, "/obras/nova", {"nome": "Samoa", "status": "Em andamento"}))
    html = client.get(f"/obras/{obra}").get_data(as_text=True)
    bloco = html[html.index('<div class="tab-content">'):]
    # Todas as abas são filhas diretas do tab-content (senão o Bootstrap não as esconde)
    assert bloco.count('class="tab-pane') == 9
    assert '<div class="card-body p-0 table-responsive">\n  <div class="tab-pane' not in html


def test_pedido_a_fornecedor(app, client):
    forn = _id(post(client, "/fornecedores/novo", {"nome": "Cimentos SA", "ativo": "1"}))
    obra = _id(post(client, "/obras/nova", {"nome": "Samoa", "status": "Em andamento"}))
    ped = _id(post(client, "/pedidos/novo", {"fornecedor_id": forn, "obra_id": obra, "descricao": "200 sacos de cimento",
                                            "valor": "6.000,00", "status": "Pendente", "previsao_entrega": "2020-01-01"}))
    html = client.get(f"/pedidos/{ped}").get_data(as_text=True)
    assert "200 sacos de cimento" in html and "atrasado" in html and "Pedido registrado" in html
    # Acompanhamento: muda status com anotação
    post(client, f"/pedidos/{ped}/acompanhamento", {"status": "Em trânsito", "observacao": "Sai sexta"})
    # Documento no pedido
    post(client, "/documentos/novo", {"entidade": "pedido", "entidade_id": ped, "voltar": f"/pedidos/{ped}",
                                      "arquivos": [(io.BytesIO(b"oc"), "ordem.pdf")]}, content_type="multipart/form-data")
    # Pagamento ligado ao pedido (pré-preenchido)
    form = client.get(f"/financeiro/novo?pedido={ped}").get_data(as_text=True)
    assert "200 sacos de cimento" in form and 'value="6000,00"' in form
    post(client, "/financeiro/novo", {"tipo": "saida", "descricao": "Pgto cimento", "valor": "2.000,00",
                                      "data": "2026-09-30", "pedido_id": ped})
    with app.app_context():
        p = db.session.get(Pedido, ped)
        assert p.status == "Em trânsito" and len(p.historico) == 2
        assert str(p.pago) == "2000" and p.pagamentos[0].fornecedor_id == forn
        assert p.pagamentos[0].obra_id == obra
    html = client.get(f"/pedidos/{ped}").get_data(as_text=True)
    assert "Sai sexta" in html and "ordem" in html
    for url in ["/pedidos", "/pedidos?status=abertos", "/pedidos?status=atrasados", f"/fornecedores/{forn}",
                f"/obras/{obra}", "/", f"/pedidos/{ped}/editar"]:
        r = client.get(url)
        assert r.status_code == 200 and "200 sacos de cimento" in r.get_data(as_text=True), url
    post(client, f"/pedidos/{ped}/acompanhamento", {"status": "Entregue"})
    with app.app_context():
        assert db.session.get(Pedido, ped).data_entrega is not None
    assert "200 sacos" not in client.get("/pedidos?status=abertos").get_data(as_text=True)
