"""Notas fiscais, contratos, funcionários e pagamentos de funcionários."""
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import func, or_

from .models import (
    CATEGORIAS_DOCUMENTO, CATEGORIAS_ENTRADA, CATEGORIAS_SAIDA, CONTRATO_STATUS, CONTRATO_TIPOS, FORMAS_PAGAMENTO,
    TIPOS_CONTRATACAO, TIPOS_PAGAMENTO, Contrato, Documento, Fornecedor, Funcionario, Lancamento, NotaFiscal,
    PagamentoFuncionario, db,
)
from .routes import obras_opcoes
from .utils import (
    cent, parse_data, parse_int, parse_valor, remover_anexo, render_sem_salvar, salvar_anexo, url_segura,
)

bp_cad = Blueprint("cad", __name__)


def _texto(campo):
    return request.form.get(campo, "").strip()


# ---------------------------------------------------------------- Notas fiscais

@bp_cad.route("/notas")
@login_required
def notas():
    q = NotaFiscal.query
    tipo, obra, busca = request.args.get("tipo", ""), request.args.get("obra", ""), request.args.get("busca", "")
    if tipo:
        q = q.filter_by(tipo=tipo)
    if obra == "geral":
        q = q.filter(NotaFiscal.obra_id.is_(None))
    elif obra:
        q = q.filter_by(obra_id=parse_int(obra))
    if busca:
        like = f"%{busca}%"
        q = q.filter(or_(NotaFiscal.numero.ilike(like), NotaFiscal.parceiro.ilike(like),
                         NotaFiscal.descricao.ilike(like), NotaFiscal.cpf_cnpj.ilike(like)))
    notas = q.order_by(NotaFiscal.data_emissao.desc(), NotaFiscal.id.desc()).all()
    total = cent(sum(n.valor_centavos for n in notas))
    return render_template("notas/lista.html", notas=notas, total=total, obras=obras_opcoes(),
                           filtros={"tipo": tipo, "obra": obra, "busca": busca})


@bp_cad.route("/notas/nova", methods=["GET", "POST"])
@bp_cad.route("/notas/<int:id>/editar", methods=["GET", "POST"])
@login_required
def nota_form(id=None):
    nota = db.get_or_404(NotaFiscal, id) if id else NotaFiscal(
        tipo=request.args.get("tipo", "entrada"), data_emissao=date.today(),
        obra_id=parse_int(request.args.get("obra")), fornecedor_id=parse_int(request.args.get("fornecedor")),
    )
    gerar = nota.lancamento is not None if id else True
    categoria = nota.lancamento.categoria if nota.lancamento else ""
    forma = nota.lancamento.forma_pagamento if nota.lancamento else ""
    if request.method == "POST":
        gerar = bool(request.form.get("gerar_lancamento"))
        categoria, forma = _texto("categoria"), _texto("forma_pagamento")
        try:
            nota.tipo = request.form.get("tipo") if request.form.get("tipo") in ("entrada", "saida") else "entrada"
            nota.numero = _texto("numero")
            if not nota.numero:
                raise ValueError("Informe o número da nota.")
            nota.serie = _texto("serie")
            nota.parceiro = _texto("parceiro")
            nota.cpf_cnpj = _texto("cpf_cnpj")
            nota.valor = parse_valor(request.form.get("valor"))
            nota.data_emissao = parse_data(request.form.get("data_emissao")) or date.today()
            nota.descricao = _texto("descricao")
            nota.obra_id = parse_int(request.form.get("obra_id"))
            nota.fornecedor_id = parse_int(request.form.get("fornecedor_id"))
            fornecedor = db.session.get(Fornecedor, nota.fornecedor_id) if nota.fornecedor_id else None
            if fornecedor:
                nota.parceiro = nota.parceiro or fornecedor.nome
                nota.cpf_cnpj = nota.cpf_cnpj or fornecedor.cpf_cnpj
            salvar_anexo(nota)
        except ValueError as e:
            flash(str(e), "danger")
            return render_sem_salvar(_render_nota, nota, gerar, categoria, forma)

        if gerar:
            l = nota.lancamento or Lancamento()
            # Nota de entrada (compra) = saída de dinheiro; nota de saída (emitida) = entrada de dinheiro.
            l.tipo = "saida" if nota.tipo == "entrada" else "entrada"
            l.descricao = f"NF {nota.numero}" + (f" - {nota.parceiro}" if nota.parceiro else "")
            l.valor = nota.valor
            l.data = nota.data_emissao
            l.obra_id = nota.obra_id
            l.fornecedor_id = nota.fornecedor_id
            l.categoria = categoria
            l.forma_pagamento = forma
            nota.lancamento = l
        elif nota.lancamento:
            db.session.delete(nota.lancamento)
            nota.lancamento = None
        db.session.add(nota)
        db.session.commit()
        flash("Nota fiscal salva.", "success")
        return redirect(url_segura(request.args.get("voltar")) or url_for("cad.notas"))
    return _render_nota(nota, gerar, categoria, forma)


def _render_nota(nota, gerar, categoria, forma):
    return render_template(
        "notas/form.html", nota=nota, gerar=gerar, categoria=categoria, forma=forma,
        obras=obras_opcoes(), categorias_entrada=CATEGORIAS_ENTRADA,
        categorias_saida=CATEGORIAS_SAIDA, formas=FORMAS_PAGAMENTO,
        fornecedores=Fornecedor.query.order_by(Fornecedor.nome).all(),
    )


@bp_cad.route("/notas/<int:id>/excluir", methods=["POST"])
@login_required
def nota_excluir(id):
    nota = db.get_or_404(NotaFiscal, id)
    remover_anexo(nota.arquivo)
    db.session.delete(nota)
    db.session.commit()
    flash("Nota fiscal excluída (e o lançamento financeiro ligado a ela).", "success")
    return redirect(url_segura(request.form.get("voltar")) or url_for("cad.notas"))


# ---------------------------------------------------------------- Contratos

@bp_cad.route("/contratos")
@login_required
def contratos():
    q = Contrato.query
    status, obra, busca = request.args.get("status", ""), request.args.get("obra", ""), request.args.get("busca", "")
    if status:
        q = q.filter_by(status=status)
    if obra == "geral":
        q = q.filter(Contrato.obra_id.is_(None))
    elif obra:
        q = q.filter_by(obra_id=parse_int(obra))
    if busca:
        like = f"%{busca}%"
        q = q.filter(or_(Contrato.titulo.ilike(like), Contrato.parte.ilike(like), Contrato.descricao.ilike(like)))
    return render_template(
        "contratos/lista.html", contratos=q.order_by(Contrato.data_inicio.desc(), Contrato.id.desc()).all(),
        obras=obras_opcoes(), status_opcoes=CONTRATO_STATUS, hoje=date.today(),
        filtros={"status": status, "obra": obra, "busca": busca},
    )


@bp_cad.route("/contratos/novo", methods=["GET", "POST"])
@bp_cad.route("/contratos/<int:id>/editar", methods=["GET", "POST"])
@login_required
def contrato_form(id=None):
    c = db.get_or_404(Contrato, id) if id else Contrato(
        status="Vigente", obra_id=parse_int(request.args.get("obra")), data_inicio=date.today()
    )
    if request.method == "POST":
        try:
            c.titulo = _texto("titulo")
            if not c.titulo:
                raise ValueError("Informe o título do contrato.")
            c.tipo = _texto("tipo")
            c.parte = _texto("parte")
            c.cpf_cnpj = _texto("cpf_cnpj")
            c.valor = parse_valor(request.form.get("valor"))
            c.data_inicio = parse_data(request.form.get("data_inicio"))
            c.data_fim = parse_data(request.form.get("data_fim"))
            c.status = _texto("status") or "Vigente"
            c.descricao = request.form.get("descricao", "")
            c.obra_id = parse_int(request.form.get("obra_id"))
            salvar_anexo(c)
        except ValueError as e:
            flash(str(e), "danger")
            return render_sem_salvar(_render_contrato, c)
        db.session.add(c)
        db.session.commit()
        flash("Contrato salvo.", "success")
        return redirect(url_segura(request.args.get("voltar")) or url_for("cad.contratos"))
    return _render_contrato(c)


def _render_contrato(c):
    return render_template("contratos/form.html", c=c, obras=obras_opcoes(),
                           tipos=CONTRATO_TIPOS, status_opcoes=CONTRATO_STATUS)


@bp_cad.route("/contratos/<int:id>/excluir", methods=["POST"])
@login_required
def contrato_excluir(id):
    c = db.get_or_404(Contrato, id)
    remover_anexo(c.arquivo)
    db.session.delete(c)
    db.session.commit()
    flash("Contrato excluído.", "success")
    return redirect(url_segura(request.form.get("voltar")) or url_for("cad.contratos"))


# ---------------------------------------------------------------- Funcionários

@bp_cad.route("/funcionarios")
@login_required
def funcionarios():
    situacao = request.args.get("situacao", "ativos")
    q = Funcionario.query
    if situacao == "ativos":
        q = q.filter_by(ativo=True)
    elif situacao == "inativos":
        q = q.filter_by(ativo=False)
    funcionarios = q.order_by(Funcionario.nome).all()
    pagos = dict(
        db.session.query(PagamentoFuncionario.funcionario_id, func.sum(PagamentoFuncionario.valor_centavos))
        .group_by(PagamentoFuncionario.funcionario_id).all()
    )
    return render_template("funcionarios/lista.html", funcionarios=funcionarios, situacao=situacao,
                           pagos={k: cent(v) for k, v in pagos.items()})


@bp_cad.route("/funcionarios/novo", methods=["GET", "POST"])
@bp_cad.route("/funcionarios/<int:id>/editar", methods=["GET", "POST"])
@login_required
def funcionario_form(id=None):
    f = db.get_or_404(Funcionario, id) if id else Funcionario(ativo=True, tipo_contratacao="CLT")
    if request.method == "POST":
        try:
            f.nome = _texto("nome")
            if not f.nome:
                raise ValueError("Informe o nome do funcionário.")
            f.cpf = _texto("cpf")
            f.cargo = _texto("cargo")
            f.telefone = _texto("telefone")
            f.tipo_contratacao = _texto("tipo_contratacao")
            f.salario = parse_valor(request.form.get("salario"))
            f.chave_pix = _texto("chave_pix")
            f.dados_bancarios = _texto("dados_bancarios")
            f.data_admissao = parse_data(request.form.get("data_admissao"))
            f.data_demissao = parse_data(request.form.get("data_demissao"))
            f.ativo = bool(request.form.get("ativo"))
            f.obra_id = parse_int(request.form.get("obra_id"))
            f.observacoes = request.form.get("observacoes", "")
        except ValueError as e:
            flash(str(e), "danger")
            return render_sem_salvar(_render_funcionario, f)
        db.session.add(f)
        db.session.commit()
        flash("Funcionário salvo.", "success")
        return redirect(url_for("cad.funcionario_detalhe", id=f.id))
    return _render_funcionario(f)


def _render_funcionario(f):
    return render_template("funcionarios/form.html", f=f, obras=obras_opcoes(), tipos=TIPOS_CONTRATACAO)


@bp_cad.route("/funcionarios/<int:id>")
@login_required
def funcionario_detalhe(id):
    f = db.get_or_404(Funcionario, id)
    pagamentos = sorted(f.pagamentos, key=lambda p: (p.data_pagamento, p.id), reverse=True)
    docs = (Documento.query.filter_by(entidade="funcionario", entidade_id=id)
            .order_by(Documento.categoria, Documento.titulo).all())
    return render_template("funcionarios/detalhe.html", f=f, pagamentos=pagamentos,
                           total=cent(sum(p.valor_centavos for p in pagamentos)),
                           docs=docs, categorias_doc=CATEGORIAS_DOCUMENTO["funcionario"])


@bp_cad.route("/funcionarios/<int:id>/excluir", methods=["POST"])
@login_required
def funcionario_excluir(id):
    f = db.get_or_404(Funcionario, id)
    if f.pagamentos:
        flash("Esse funcionário tem pagamentos registrados. Para manter o histórico, "
              "marque-o como inativo em vez de excluir.", "warning")
        return redirect(url_for("cad.funcionario_detalhe", id=id))
    for d in Documento.query.filter_by(entidade="funcionario", entidade_id=id).all():
        remover_anexo(d.arquivo)
        db.session.delete(d)
    db.session.delete(f)
    db.session.commit()
    flash("Funcionário excluído.", "success")
    return redirect(url_for("cad.funcionarios"))


# ---------------------------------------------------------------- Pagamentos de funcionários

@bp_cad.route("/pagamentos")
@login_required
def pagamentos():
    q = PagamentoFuncionario.query
    competencia = request.args.get("competencia", "")
    obra = request.args.get("obra", "")
    funcionario = request.args.get("funcionario", "")
    if competencia:
        q = q.filter_by(competencia=competencia)
    if obra == "geral":
        q = q.filter(PagamentoFuncionario.obra_id.is_(None))
    elif obra:
        q = q.filter_by(obra_id=parse_int(obra))
    if funcionario:
        q = q.filter_by(funcionario_id=parse_int(funcionario))
    lista = q.order_by(PagamentoFuncionario.data_pagamento.desc(), PagamentoFuncionario.id.desc()).all()
    return render_template(
        "pagamentos/lista.html", pagamentos=lista, total=cent(sum(p.valor_centavos for p in lista)),
        obras=obras_opcoes(), funcionarios=Funcionario.query.order_by(Funcionario.nome).all(),
        filtros={"competencia": competencia, "obra": obra, "funcionario": funcionario},
    )


@bp_cad.route("/pagamentos/novo", methods=["GET", "POST"])
@bp_cad.route("/pagamentos/<int:id>/editar", methods=["GET", "POST"])
@login_required
def pagamento_form(id=None):
    if id:
        p = db.get_or_404(PagamentoFuncionario, id)
    else:
        func_id = parse_int(request.args.get("funcionario"))
        funcionario = db.session.get(Funcionario, func_id) if func_id else None
        p = PagamentoFuncionario(
            funcionario_id=func_id, data_pagamento=date.today(), tipo="Salário", forma_pagamento="PIX",
            competencia=date.today().strftime("%Y-%m"),
            obra_id=funcionario.obra_id if funcionario else parse_int(request.args.get("obra")),
        )
        if funcionario:
            p.valor = funcionario.salario
    if request.method == "POST":
        try:
            p.funcionario_id = parse_int(request.form.get("funcionario_id"))
            if not p.funcionario_id or not db.session.get(Funcionario, p.funcionario_id):
                raise ValueError("Escolha o funcionário.")
            p.tipo = _texto("tipo")
            p.competencia = _texto("competencia")
            p.valor = parse_valor(request.form.get("valor"))
            if p.valor <= 0:
                raise ValueError("Informe um valor maior que zero.")
            p.data_pagamento = parse_data(request.form.get("data_pagamento")) or date.today()
            p.forma_pagamento = _texto("forma_pagamento")
            p.obra_id = parse_int(request.form.get("obra_id"))
            p.observacao = _texto("observacao")
            salvar_anexo(p)
        except ValueError as e:
            flash(str(e), "danger")
            return render_sem_salvar(_render_pagamento, p)

        # Todo pagamento de funcionário gera automaticamente uma saída no financeiro.
        funcionario = db.session.get(Funcionario, p.funcionario_id)
        l = p.lancamento or Lancamento()
        l.tipo = "saida"
        l.descricao = f"{p.tipo} - {funcionario.nome}" + (f" ({p.competencia})" if p.competencia else "")
        l.categoria = "Mão de obra / Folha de pagamento"
        l.valor = p.valor
        l.data = p.data_pagamento
        l.obra_id = p.obra_id
        l.forma_pagamento = p.forma_pagamento
        p.lancamento = l
        db.session.add(p)
        db.session.commit()
        flash("Pagamento registrado e lançado no financeiro.", "success")
        if request.form.get("continuar"):
            return redirect(url_for("cad.pagamento_form"))
        return redirect(url_segura(request.args.get("voltar")) or url_for("cad.pagamentos"))
    return _render_pagamento(p)


def _render_pagamento(p):
    return render_template(
        "pagamentos/form.html", p=p, obras=obras_opcoes(), tipos=TIPOS_PAGAMENTO, formas=FORMAS_PAGAMENTO,
        funcionarios=Funcionario.query.filter(
            or_(Funcionario.ativo.is_(True), Funcionario.id == p.funcionario_id)
        ).order_by(Funcionario.nome).all(),
    )


@bp_cad.route("/pagamentos/<int:id>/excluir", methods=["POST"])
@login_required
def pagamento_excluir(id):
    p = db.get_or_404(PagamentoFuncionario, id)
    remover_anexo(p.arquivo)
    db.session.delete(p)
    db.session.commit()
    flash("Pagamento excluído (e a saída correspondente no financeiro).", "success")
    return redirect(url_segura(request.form.get("voltar")) or url_for("cad.pagamentos"))
