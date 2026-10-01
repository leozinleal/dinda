"""Documentos (anexos de todas as áreas), clientes, vendas, fornecedores e jurídico."""
import os
from datetime import date, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from .models import (
    CATEGORIAS_DOCUMENTO, CATEGORIAS_FORNECEDOR, ENTIDADES_DOCUMENTO, JURIDICO_STATUS, PEDIDO_STATUS,
    PEDIDO_STATUS_FINAIS, Cliente, Contrato, Documento, Fornecedor, Funcionario, Lancamento, NotaFiscal, Obra,
    Pedido, PedidoHistorico, VENDA_STATUS, Venda, db,
)
from .routes import obras_opcoes
from .utils import (
    cent, gravar_arquivo, parse_data, parse_int, parse_valor, remover_anexo, render_sem_salvar,
    salvar_anexo, url_segura,
)

bp_com = Blueprint("com", __name__)


def _texto(campo):
    return request.form.get(campo, "").strip()


def _like(q, busca, *colunas):
    if busca:
        like = f"%{busca}%"
        q = q.filter(or_(*[c.ilike(like) for c in colunas]))
    return q


# ---------------------------------------------------------------- Documentos

def documentos_de(entidade, entidade_id=None):
    q = Documento.query.filter_by(entidade=entidade)
    if entidade_id is not None:
        q = q.filter_by(entidade_id=entidade_id)
    return q.order_by(Documento.categoria, Documento.titulo).all()


def dono_documento(doc):
    """(rótulo, url) de onde o documento está anexado."""
    rotas = {
        "obra": (Obra, "main.obra_detalhe", lambda o: o.nome),
        "cliente": (Cliente, "com.cliente_detalhe", lambda c: c.nome),
        "venda": (Venda, "com.venda_detalhe", lambda v: f"{v.cliente.nome} – {v.unidade}"),
        "fornecedor": (Fornecedor, "com.fornecedor_detalhe", lambda f: f.nome_exibicao),
        "funcionario": (Funcionario, "cad.funcionario_detalhe", lambda f: f.nome),
        "pedido": (Pedido, "com.pedido_detalhe", lambda p: f"{p.descricao} ({p.fornecedor.nome_exibicao})"),
    }
    if doc.entidade == "empresa":
        return "Empresa", url_for("main.empresa")
    if doc.entidade == "juridico":
        return "Jurídico", url_for("com.juridico")
    modelo, rota, nome = rotas[doc.entidade]
    obj = db.session.get(modelo, doc.entidade_id)
    if obj is None:
        return ENTIDADES_DOCUMENTO[doc.entidade], None
    return f"{ENTIDADES_DOCUMENTO[doc.entidade]}: {nome(obj)}", url_for(rota, id=obj.id)


def _preencher_documento(doc):
    doc.categoria = _texto("categoria")
    doc.descricao = request.form.get("descricao", "")
    doc.data_documento = parse_data(request.form.get("data_documento"))
    doc.validade = parse_data(request.form.get("validade"))
    doc.parte = _texto("parte")
    doc.status = _texto("status")
    if doc.entidade == "juridico":
        doc.obra_id = parse_int(request.form.get("obra_id"))


@bp_com.route("/documentos/novo", methods=["POST"])
@login_required
def documento_novo():
    entidade = request.form.get("entidade")
    if entidade not in ENTIDADES_DOCUMENTO:
        abort(400)
    entidade_id = parse_int(request.form.get("entidade_id"))
    voltar = url_segura(request.form.get("voltar")) or url_for("com.documentos")
    arquivos = [a for a in request.files.getlist("arquivos") if a and a.filename]
    if not arquivos:
        flash("Escolha pelo menos um arquivo para anexar.", "danger")
        return redirect(voltar)
    titulo = _texto("titulo")
    salvos = []
    try:
        for arq in arquivos:
            nome_disco, nome_original = gravar_arquivo(arq)
            salvos.append(nome_disco)
            base = os.path.splitext(nome_original)[0]
            doc = Documento(entidade=entidade, entidade_id=entidade_id, arquivo=nome_disco,
                            arquivo_nome=nome_original)
            doc.titulo = (f"{titulo} – {base}" if len(arquivos) > 1 else titulo) if titulo else base
            _preencher_documento(doc)
            db.session.add(doc)
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        for nome in salvos:
            remover_anexo(nome)
        flash(str(e), "danger")
        return redirect(voltar)
    flash(f"{len(arquivos)} documento(s) anexado(s).", "success")
    return redirect(voltar)


@bp_com.route("/documentos/<int:id>/editar", methods=["GET", "POST"])
@login_required
def documento_form(id):
    doc = db.get_or_404(Documento, id)
    if request.method == "POST":
        try:
            doc.titulo = _texto("titulo") or doc.titulo
            _preencher_documento(doc)
            salvar_anexo(doc)
            if not doc.arquivo:
                raise ValueError("O documento precisa ter um arquivo.")
        except ValueError as e:
            flash(str(e), "danger")
            return render_sem_salvar(_render_documento, doc)
        db.session.commit()
        flash("Documento atualizado.", "success")
        return redirect(url_segura(request.args.get("voltar")) or dono_documento(doc)[1] or url_for("com.documentos"))
    return _render_documento(doc)


def _render_documento(doc):
    return render_template(
        "documentos/form.html", doc=doc, categorias=CATEGORIAS_DOCUMENTO[doc.entidade],
        obras=obras_opcoes(), status_opcoes=JURIDICO_STATUS, dono=dono_documento(doc),
    )


@bp_com.route("/documentos/<int:id>/excluir", methods=["POST"])
@login_required
def documento_excluir(id):
    doc = db.get_or_404(Documento, id)
    voltar = url_segura(request.form.get("voltar")) or dono_documento(doc)[1] or url_for("com.documentos")
    remover_anexo(doc.arquivo)
    db.session.delete(doc)
    db.session.commit()
    flash("Documento excluído.", "success")
    return redirect(voltar)


@bp_com.route("/documentos")
@login_required
def documentos():
    """Busca em todos os documentos do sistema."""
    f = {k: request.args.get(k, "") for k in ("entidade", "categoria", "busca", "vencimento")}
    q = Documento.query
    if f["entidade"] in ENTIDADES_DOCUMENTO:
        q = q.filter_by(entidade=f["entidade"])
    if f["categoria"]:
        q = q.filter_by(categoria=f["categoria"])
    q = _like(q, f["busca"], Documento.titulo, Documento.descricao, Documento.arquivo_nome, Documento.parte)
    hoje = date.today()
    if f["vencimento"] == "vencidos":
        q = q.filter(Documento.validade < hoje)
    elif f["vencimento"] == "30dias":
        q = q.filter(Documento.validade >= hoje, Documento.validade <= hoje + timedelta(days=30))
    docs = q.order_by(Documento.criado_em.desc()).limit(500).all()
    categorias = sorted({c for lista in CATEGORIAS_DOCUMENTO.values() for c in lista})
    return render_template("documentos/busca.html", docs=docs, filtros=f, hoje=hoje,
                           entidades=ENTIDADES_DOCUMENTO, categorias=categorias)


# ---------------------------------------------------------------- Jurídico

@bp_com.route("/juridico")
@login_required
def juridico():
    f = {k: request.args.get(k, "") for k in ("categoria", "status", "obra", "busca")}
    q = Documento.query.filter_by(entidade="juridico")
    if f["categoria"]:
        q = q.filter_by(categoria=f["categoria"])
    if f["status"]:
        q = q.filter_by(status=f["status"])
    if f["obra"]:
        q = q.filter_by(obra_id=parse_int(f["obra"]))
    q = _like(q, f["busca"], Documento.titulo, Documento.descricao, Documento.parte, Documento.arquivo_nome)
    return render_template(
        "juridico/lista.html", docs=q.order_by(Documento.criado_em.desc()).all(), filtros=f,
        categorias=CATEGORIAS_DOCUMENTO["juridico"], status_opcoes=JURIDICO_STATUS, obras=obras_opcoes(),
        hoje=date.today(), contratos_vigentes=Contrato.query.filter_by(status="Vigente").count(),
    )


# ---------------------------------------------------------------- Clientes

@bp_com.route("/clientes")
@login_required
def clientes():
    busca = request.args.get("busca", "")
    q = _like(Cliente.query, busca, Cliente.nome, Cliente.cpf_cnpj, Cliente.telefone, Cliente.email)
    lista = q.order_by(Cliente.nome).all()
    vendas = dict(
        db.session.query(Venda.cliente_id, func.count(Venda.id)).group_by(Venda.cliente_id).all()
    )
    return render_template("clientes/lista.html", clientes=lista, busca=busca, vendas=vendas)


@bp_com.route("/clientes/novo", methods=["GET", "POST"])
@bp_com.route("/clientes/<int:id>/editar", methods=["GET", "POST"])
@login_required
def cliente_form(id=None):
    c = db.get_or_404(Cliente, id) if id else Cliente(tipo_pessoa="PF")
    if request.method == "POST":
        try:
            c.nome = _texto("nome")
            if not c.nome:
                raise ValueError("Informe o nome do cliente.")
            for campo in ("tipo_pessoa", "cpf_cnpj", "rg", "estado_civil", "profissao", "telefone",
                          "email", "endereco"):
                setattr(c, campo, _texto(campo))
            c.data_nascimento = parse_data(request.form.get("data_nascimento"))
            c.observacoes = request.form.get("observacoes", "")
        except ValueError as e:
            flash(str(e), "danger")
            return render_sem_salvar(render_template, "clientes/form.html", c=c)
        db.session.add(c)
        db.session.commit()
        flash("Cliente salvo.", "success")
        return redirect(url_for("com.cliente_detalhe", id=c.id))
    return render_template("clientes/form.html", c=c)


@bp_com.route("/clientes/<int:id>")
@login_required
def cliente_detalhe(id):
    c = db.get_or_404(Cliente, id)
    vendas = sorted(c.vendas, key=lambda v: v.data_venda, reverse=True)
    return render_template(
        "clientes/detalhe.html", c=c, vendas=vendas,
        total_vendas=sum((v.valor for v in vendas if v.status != "Distratada"), cent(0)),
        total_recebido=sum((v.recebido for v in vendas), cent(0)),
        docs=documentos_de("cliente", c.id), categorias_doc=CATEGORIAS_DOCUMENTO["cliente"],
    )


@bp_com.route("/clientes/<int:id>/excluir", methods=["POST"])
@login_required
def cliente_excluir(id):
    c = db.get_or_404(Cliente, id)
    if c.vendas or Lancamento.query.filter_by(cliente_id=id).count():
        flash("Esse cliente tem vendas ou lançamentos registrados e não pode ser excluído.", "warning")
        return redirect(url_for("com.cliente_detalhe", id=id))
    for d in documentos_de("cliente", id):
        remover_anexo(d.arquivo)
        db.session.delete(d)
    db.session.delete(c)
    db.session.commit()
    flash("Cliente excluído.", "success")
    return redirect(url_for("com.clientes"))


# ---------------------------------------------------------------- Vendas

@bp_com.route("/vendas")
@login_required
def vendas():
    f = {k: request.args.get(k, "") for k in ("obra", "status", "busca")}
    q = Venda.query.join(Cliente)
    if f["obra"]:
        q = q.filter(Venda.obra_id == parse_int(f["obra"]))
    if f["status"]:
        q = q.filter(Venda.status == f["status"])
    q = _like(q, f["busca"], Cliente.nome, Venda.unidade, Venda.corretor)
    lista = q.order_by(Venda.data_venda.desc(), Venda.id.desc()).all()
    ativas = [v for v in lista if v.status != "Distratada"]
    return render_template(
        "vendas/lista.html", vendas=lista, filtros=f, obras=obras_opcoes(), status_opcoes=VENDA_STATUS,
        total=sum((v.valor for v in ativas), cent(0)),
        recebido=sum((v.recebido for v in ativas), cent(0)),
    )


@bp_com.route("/vendas/nova", methods=["GET", "POST"])
@bp_com.route("/vendas/<int:id>/editar", methods=["GET", "POST"])
@login_required
def venda_form(id=None):
    v = db.get_or_404(Venda, id) if id else Venda(
        data_venda=date.today(), status="Contrato assinado",
        cliente_id=parse_int(request.args.get("cliente")), obra_id=parse_int(request.args.get("obra")),
    )
    if request.method == "POST":
        try:
            v.cliente_id = parse_int(request.form.get("cliente_id"))
            if not v.cliente_id or not db.session.get(Cliente, v.cliente_id):
                raise ValueError("Escolha o cliente (cadastre-o antes, se for novo).")
            v.obra_id = parse_int(request.form.get("obra_id"))
            v.unidade = _texto("unidade")
            v.valor = parse_valor(request.form.get("valor"))
            if v.valor <= 0:
                raise ValueError("Informe o valor da venda.")
            v.data_venda = parse_data(request.form.get("data_venda")) or date.today()
            v.status = _texto("status") or "Contrato assinado"
            v.corretor = _texto("corretor")
            v.condicoes = request.form.get("condicoes", "")
            v.observacoes = request.form.get("observacoes", "")
        except ValueError as e:
            flash(str(e), "danger")
            return render_sem_salvar(_render_venda, v)
        db.session.add(v)
        db.session.commit()
        flash("Venda salva.", "success")
        return redirect(url_for("com.venda_detalhe", id=v.id))
    return _render_venda(v)


def _render_venda(v):
    return render_template("vendas/form.html", v=v, obras=obras_opcoes(), status_opcoes=VENDA_STATUS,
                           clientes=Cliente.query.order_by(Cliente.nome).all())


@bp_com.route("/vendas/<int:id>")
@login_required
def venda_detalhe(id):
    v = db.get_or_404(Venda, id)
    recebimentos = sorted(v.recebimentos, key=lambda l: (l.data, l.id), reverse=True)
    return render_template("vendas/detalhe.html", v=v, recebimentos=recebimentos,
                           docs=documentos_de("venda", v.id), categorias_doc=CATEGORIAS_DOCUMENTO["venda"])


@bp_com.route("/vendas/<int:id>/excluir", methods=["POST"])
@login_required
def venda_excluir(id):
    v = db.get_or_404(Venda, id)
    if v.recebimentos:
        flash("Essa venda tem recebimentos lançados. Mude o status para 'Distratada' em vez de excluir.", "warning")
        return redirect(url_for("com.venda_detalhe", id=id))
    for d in documentos_de("venda", id):
        remover_anexo(d.arquivo)
        db.session.delete(d)
    db.session.delete(v)
    db.session.commit()
    flash("Venda excluída.", "success")
    return redirect(url_for("com.vendas"))


# ---------------------------------------------------------------- Fornecedores

@bp_com.route("/fornecedores")
@login_required
def fornecedores():
    f = {k: request.args.get(k, "") for k in ("categoria", "busca", "situacao")}
    q = Fornecedor.query
    if f["categoria"]:
        q = q.filter_by(categoria=f["categoria"])
    if f["situacao"] != "todos":
        q = q.filter_by(ativo=True)
    q = _like(q, f["busca"], Fornecedor.nome, Fornecedor.nome_fantasia, Fornecedor.cpf_cnpj, Fornecedor.contato)
    pago = dict(
        db.session.query(Lancamento.fornecedor_id, func.sum(Lancamento.valor_centavos))
        .filter(Lancamento.tipo == "saida", Lancamento.fornecedor_id.isnot(None))
        .group_by(Lancamento.fornecedor_id).all()
    )
    return render_template("fornecedores/lista.html", fornecedores=q.order_by(Fornecedor.nome).all(),
                           filtros=f, categorias=CATEGORIAS_FORNECEDOR,
                           pago={k: cent(v) for k, v in pago.items()})


@bp_com.route("/fornecedores/novo", methods=["GET", "POST"])
@bp_com.route("/fornecedores/<int:id>/editar", methods=["GET", "POST"])
@login_required
def fornecedor_form(id=None):
    fo = db.get_or_404(Fornecedor, id) if id else Fornecedor(ativo=True)
    if request.method == "POST":
        fo.nome = _texto("nome")
        if not fo.nome:
            flash("Informe o nome / razão social do fornecedor.", "danger")
            return render_sem_salvar(render_template, "fornecedores/form.html", fo=fo,
                                     categorias=CATEGORIAS_FORNECEDOR)
        for campo in ("nome_fantasia", "cpf_cnpj", "categoria", "contato", "telefone", "email", "endereco",
                      "chave_pix", "dados_bancarios"):
            setattr(fo, campo, _texto(campo))
        fo.observacoes = request.form.get("observacoes", "")
        fo.ativo = bool(request.form.get("ativo"))
        db.session.add(fo)
        db.session.commit()
        flash("Fornecedor salvo.", "success")
        return redirect(url_for("com.fornecedor_detalhe", id=fo.id))
    return render_template("fornecedores/form.html", fo=fo, categorias=CATEGORIAS_FORNECEDOR)


@bp_com.route("/fornecedores/<int:id>")
@login_required
def fornecedor_detalhe(id):
    fo = db.get_or_404(Fornecedor, id)
    lancs = (Lancamento.query.filter_by(fornecedor_id=id)
             .order_by(Lancamento.data.desc(), Lancamento.id.desc()).all())
    return render_template(
        "fornecedores/detalhe.html", fo=fo, lancamentos=lancs,
        total_pago=cent(sum(l.valor_centavos for l in lancs if l.tipo == "saida")),
        notas=NotaFiscal.query.filter_by(fornecedor_id=id).order_by(NotaFiscal.data_emissao.desc()).all(),
        docs=documentos_de("fornecedor", id), categorias_doc=CATEGORIAS_DOCUMENTO["fornecedor"],
        pedidos=Pedido.query.filter_by(fornecedor_id=id).order_by(Pedido.data_pedido.desc(), Pedido.id.desc()).all(),
    )


@bp_com.route("/fornecedores/<int:id>/excluir", methods=["POST"])
@login_required
def fornecedor_excluir(id):
    fo = db.get_or_404(Fornecedor, id)
    if (Lancamento.query.filter_by(fornecedor_id=id).count() or NotaFiscal.query.filter_by(fornecedor_id=id).count()
            or Pedido.query.filter_by(fornecedor_id=id).count()):
        flash("Esse fornecedor tem lançamentos, notas ou pedidos. Para manter o histórico, marque-o como inativo.", "warning")
        return redirect(url_for("com.fornecedor_detalhe", id=id))
    for d in documentos_de("fornecedor", id):
        remover_anexo(d.arquivo)
        db.session.delete(d)
    db.session.delete(fo)
    db.session.commit()
    flash("Fornecedor excluído.", "success")
    return redirect(url_for("com.fornecedores"))


# ---------------------------------------------------------------- Pedidos a fornecedores

def _registrar_historico(pedido, status, observacao=""):
    pedido.historico.append(PedidoHistorico(
        status=status, observacao=observacao,
        usuario=getattr(current_user, "nome", "") or "",
    ))


@bp_com.route("/pedidos")
@login_required
def pedidos():
    f = {k: request.args.get(k, "") for k in ("fornecedor", "obra", "status", "busca")}
    q = Pedido.query.join(Fornecedor)
    if f["fornecedor"]:
        q = q.filter(Pedido.fornecedor_id == parse_int(f["fornecedor"]))
    if f["obra"]:
        q = q.filter(Pedido.obra_id == parse_int(f["obra"]))
    if f["status"] == "abertos":
        q = q.filter(Pedido.status.notin_(PEDIDO_STATUS_FINAIS))
    elif f["status"] == "atrasados":
        q = q.filter(Pedido.status.notin_(PEDIDO_STATUS_FINAIS), Pedido.previsao_entrega < date.today())
    elif f["status"]:
        q = q.filter(Pedido.status == f["status"])
    q = _like(q, f["busca"], Pedido.descricao, Pedido.numero, Pedido.itens, Fornecedor.nome, Fornecedor.nome_fantasia)
    lista = q.order_by(Pedido.data_pedido.desc(), Pedido.id.desc()).all()
    return render_template(
        "pedidos/lista.html", pedidos=lista, filtros=f, status_opcoes=PEDIDO_STATUS, obras=obras_opcoes(),
        fornecedores=Fornecedor.query.order_by(Fornecedor.nome).all(),
        total=sum((p.valor for p in lista if p.status != "Cancelado"), cent(0)),
    )


@bp_com.route("/pedidos/novo", methods=["GET", "POST"])
@bp_com.route("/pedidos/<int:id>/editar", methods=["GET", "POST"])
@login_required
def pedido_form(id=None):
    p = db.get_or_404(Pedido, id) if id else Pedido(
        status="Pendente", data_pedido=date.today(),
        fornecedor_id=parse_int(request.args.get("fornecedor")), obra_id=parse_int(request.args.get("obra")),
    )
    status_anterior = p.status if id else None
    if request.method == "POST":
        try:
            p.fornecedor_id = parse_int(request.form.get("fornecedor_id"))
            if not p.fornecedor_id or not db.session.get(Fornecedor, p.fornecedor_id):
                raise ValueError("Escolha o fornecedor.")
            p.descricao = _texto("descricao")
            if not p.descricao:
                raise ValueError("Descreva o pedido (ex.: 200 sacos de cimento).")
            p.obra_id = parse_int(request.form.get("obra_id"))
            p.numero = _texto("numero")
            p.itens = request.form.get("itens", "")
            p.valor = parse_valor(request.form.get("valor"))
            p.data_pedido = parse_data(request.form.get("data_pedido")) or date.today()
            p.previsao_entrega = parse_data(request.form.get("previsao_entrega"))
            p.data_entrega = parse_data(request.form.get("data_entrega"))
            p.status = _texto("status") or "Pendente"
            p.condicoes = _texto("condicoes")
            p.observacoes = request.form.get("observacoes", "")
        except ValueError as e:
            flash(str(e), "danger")
            return render_sem_salvar(_render_pedido, p)
        if not id:
            _registrar_historico(p, p.status, "Pedido registrado.")
        elif p.status != status_anterior:
            _registrar_historico(p, p.status, f"Status alterado de “{status_anterior}” para “{p.status}”.")
        if p.status == "Entregue" and not p.data_entrega:
            p.data_entrega = date.today()
        db.session.add(p)
        db.session.commit()
        flash("Pedido salvo.", "success")
        return redirect(url_for("com.pedido_detalhe", id=p.id))
    return _render_pedido(p)


def _render_pedido(p):
    return render_template(
        "pedidos/form.html", p=p, obras=obras_opcoes(), status_opcoes=PEDIDO_STATUS,
        fornecedores=Fornecedor.query.filter(
            or_(Fornecedor.ativo.is_(True), Fornecedor.id == p.fornecedor_id)).order_by(Fornecedor.nome).all(),
    )


@bp_com.route("/pedidos/<int:id>")
@login_required
def pedido_detalhe(id):
    p = db.get_or_404(Pedido, id)
    return render_template(
        "pedidos/detalhe.html", p=p, status_opcoes=PEDIDO_STATUS,
        pagamentos=sorted(p.pagamentos, key=lambda l: (l.data, l.id), reverse=True),
        docs=documentos_de("pedido", p.id), categorias_doc=CATEGORIAS_DOCUMENTO["pedido"],
    )


@bp_com.route("/pedidos/<int:id>/acompanhamento", methods=["POST"])
@login_required
def pedido_acompanhamento(id):
    """Atualiza o status e/ou registra uma anotação no histórico do pedido."""
    p = db.get_or_404(Pedido, id)
    novo = _texto("status") or p.status
    obs = _texto("observacao")
    if novo == p.status and not obs:
        flash("Escolha um novo status ou escreva uma anotação.", "warning")
        return redirect(url_for("com.pedido_detalhe", id=id))
    if novo not in PEDIDO_STATUS:
        abort(400)
    p.status = novo
    if novo == "Entregue" and not p.data_entrega:
        p.data_entrega = date.today()
    _registrar_historico(p, novo, obs)
    db.session.commit()
    flash("Acompanhamento registrado.", "success")
    return redirect(url_for("com.pedido_detalhe", id=id))


@bp_com.route("/pedidos/<int:id>/excluir", methods=["POST"])
@login_required
def pedido_excluir(id):
    p = db.get_or_404(Pedido, id)
    if p.pagamentos:
        flash("Esse pedido tem pagamentos lançados. Mude o status para 'Cancelado' em vez de excluir.", "warning")
        return redirect(url_for("com.pedido_detalhe", id=id))
    for d in documentos_de("pedido", id):
        remover_anexo(d.arquivo)
        db.session.delete(d)
    fornecedor_id = p.fornecedor_id
    db.session.delete(p)
    db.session.commit()
    flash("Pedido excluído.", "success")
    return redirect(url_for("com.fornecedor_detalhe", id=fornecedor_id))
