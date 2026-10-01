import csv
import hmac
import io
import os
import shutil
import tempfile
import time
from datetime import date, timedelta

from flask import (
    Blueprint, Response, abort, current_app, flash, redirect, render_template,
    request, send_file, send_from_directory, session, url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, or_

from .models import (
    CATEGORIAS_ENTRADA, CATEGORIAS_SAIDA, FORMAS_PAGAMENTO, OBRA_STATUS,
    CATEGORIAS_DOCUMENTO, Atividade, Cliente, Contrato, Documento, Empresa, Fornecedor, Funcionario, Lancamento,
    NotaFiscal, Obra, PagamentoFuncionario, Pedido, PEDIDO_STATUS_FINAIS, Usuario, Venda, db,
)
from .utils import (
    cent, formata_data, parse_data, parse_int, parse_valor, remover_anexo, render_sem_salvar,
    salvar_anexo, url_segura,
)

from .backup import gerar_backup
from .seguranca import (
    login_bloqueado, novo_segredo_totp, qr_totp_svg, registrar_atividade, registrar_tentativa, validar_senha,
    verificar_totp,
)

bp_auth = Blueprint("auth", __name__)
bp_main = Blueprint("main", __name__)


# ---------------------------------------------------------------- Autenticação

def _entrar(u):
    session.pop("2fa_uid", None)
    session.pop("2fa_ate", None)
    session.pop("2fa_next", None)
    login_user(u)
    session["ultimo_acesso"] = int(time.time())
    registrar_tentativa(u.email, True)
    registrar_atividade("Entrou no sistema")


@bp_auth.route("/setup", methods=["GET", "POST"])
def setup():
    if Usuario.query.count() > 0:
        return redirect(url_for("auth.login"))
    token_exigido = current_app.config.get("SETUP_TOKEN")
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        erro_senha = validar_senha(senha, email)
        if token_exigido and not hmac.compare_digest(request.form.get("token", "").strip(), token_exigido):
            flash("Código de instalação incorreto. Ele aparece no final da instalação do servidor.", "danger")
        elif not nome or not email:
            flash("Preencha nome e e-mail.", "danger")
        elif erro_senha:
            flash(erro_senha, "danger")
        elif senha != request.form.get("senha2", senha):
            flash("As senhas não conferem.", "danger")
        else:
            u = Usuario(nome=nome, email=email, is_admin=True)
            u.set_senha(senha)
            db.session.add(u)
            empresa = Empresa.get()
            empresa.razao_social = request.form.get("empresa", "").strip()
            db.session.commit()
            _entrar(u)
            flash("Bem-vinda! Sistema configurado. Recomendamos ativar a verificação em duas etapas.", "success")
            return redirect(url_for("auth.seguranca"))
    return render_template("auth/setup.html", token_exigido=bool(token_exigido))


@bp_auth.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if login_bloqueado(email):
            flash("Muitas tentativas erradas. Por segurança, aguarde 15 minutos e tente de novo.", "danger")
            return render_template("auth/login.html"), 429
        u = Usuario.query.filter_by(email=email).first()
        if u and u.ativo and u.check_senha(request.form.get("senha", "")):
            destino = url_segura(request.args.get("next"))
            if u.totp_ativo:
                session["2fa_uid"] = u.id
                session["2fa_ate"] = int(time.time()) + 300
                session["2fa_next"] = destino
                return redirect(url_for("auth.login_codigo"))
            _entrar(u)
            return redirect(destino or url_for("main.dashboard"))
        registrar_tentativa(email, False)
        flash("E-mail ou senha incorretos.", "danger")
    return render_template("auth/login.html")


@bp_auth.route("/login/codigo", methods=["GET", "POST"])
def login_codigo():
    """Segunda etapa do login: código de 6 dígitos do app autenticador."""
    uid = session.get("2fa_uid")
    if not uid or int(time.time()) > session.get("2fa_ate", 0):
        session.pop("2fa_uid", None)
        flash("Entre novamente com e-mail e senha.", "warning")
        return redirect(url_for("auth.login"))
    u = db.session.get(Usuario, uid)
    if request.method == "POST":
        if login_bloqueado(u.email):
            flash("Muitas tentativas erradas. Aguarde 15 minutos e tente de novo.", "danger")
            return render_template("auth/codigo.html"), 429
        passo = verificar_totp(u.totp_segredo, request.form.get("codigo"), u.totp_ultimo_passo)
        if passo is not None:
            u.totp_ultimo_passo = passo
            db.session.commit()
            destino = session.get("2fa_next")
            _entrar(u)
            return redirect(destino or url_for("main.dashboard"))
        registrar_tentativa(u.email, False)
        flash("Código incorreto ou expirado. Confira o app e tente de novo.", "danger")
    return render_template("auth/codigo.html")


@bp_auth.route("/logout", methods=["POST"])
@login_required
def logout():
    registrar_atividade("Saiu do sistema")
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))


@bp_auth.route("/usuarios", methods=["GET", "POST"])
@login_required
def usuarios():
    if not current_user.is_admin:
        abort(403)
    if request.method == "POST":
        acao = request.form.get("acao")
        if acao == "criar":
            email = request.form.get("email", "").strip().lower()
            senha = request.form.get("senha", "")
            nome = request.form.get("nome", "").strip()
            erro_senha = validar_senha(senha, email)
            if not nome or not email:
                flash("Preencha nome e e-mail.", "danger")
            elif erro_senha:
                flash(erro_senha, "danger")
            elif Usuario.query.filter_by(email=email).first():
                flash("Já existe um usuário com esse e-mail.", "danger")
            else:
                u = Usuario(nome=nome, email=email, is_admin=bool(request.form.get("is_admin")))
                u.set_senha(senha)
                db.session.add(u)
                db.session.commit()
                flash("Usuário criado.", "success")
        elif acao == "alternar":
            u = db.get_or_404(Usuario, parse_int(request.form.get("id")))
            if u.id == current_user.id:
                flash("Você não pode desativar o próprio usuário.", "warning")
            else:
                u.ativo = not u.ativo
                db.session.commit()
                flash("Usuário atualizado.", "success")
        return redirect(url_for("auth.usuarios"))
    return render_template("auth/usuarios.html", usuarios=Usuario.query.order_by(Usuario.nome).all())


@bp_auth.route("/minha-senha", methods=["GET", "POST"])
@login_required
def minha_senha():
    if request.method == "POST":
        nova = request.form.get("nova", "")
        erro = validar_senha(nova, current_user.email)
        if not current_user.check_senha(request.form.get("atual", "")):
            flash("Senha atual incorreta.", "danger")
        elif erro:
            flash(erro, "danger")
        elif nova != request.form.get("nova2", nova):
            flash("As senhas novas não conferem.", "danger")
        else:
            current_user.set_senha(nova)
            db.session.commit()
            registrar_atividade("Alterou a senha")
            flash("Senha alterada.", "success")
            return redirect(url_for("main.dashboard"))
    return render_template("auth/senha.html")


@bp_auth.route("/seguranca", methods=["GET", "POST"])
@login_required
def seguranca():
    """Ativar / desativar a verificação em duas etapas."""
    u = current_user
    if request.method == "POST":
        acao = request.form.get("acao")
        if acao == "ativar" and not u.totp_ativo:
            segredo = session.get("totp_novo")
            passo = verificar_totp(segredo, request.form.get("codigo"))
            if passo is None:
                flash("Código incorreto. Confira se o horário do celular está automático e tente de novo.", "danger")
            else:
                u.totp_segredo, u.totp_ativo, u.totp_ultimo_passo = segredo, True, passo
                session.pop("totp_novo", None)
                db.session.commit()
                registrar_atividade("Ativou a verificação em duas etapas")
                flash("Verificação em duas etapas ativada! A partir de agora o login pede o código do app.", "success")
                return redirect(url_for("auth.seguranca"))
        elif acao == "desativar" and u.totp_ativo:
            if not u.check_senha(request.form.get("senha", "")):
                flash("Senha incorreta.", "danger")
            elif verificar_totp(u.totp_segredo, request.form.get("codigo")) is None:
                flash("Código incorreto.", "danger")
            else:
                u.totp_segredo, u.totp_ativo, u.totp_ultimo_passo = None, False, None
                db.session.commit()
                registrar_atividade("Desativou a verificação em duas etapas")
                flash("Verificação em duas etapas desativada.", "warning")
                return redirect(url_for("auth.seguranca"))
    qr = segredo = None
    if not u.totp_ativo:
        segredo = session.get("totp_novo") or novo_segredo_totp()
        session["totp_novo"] = segredo
        emissor = (Empresa.get().nome_fantasia or Empresa.get().razao_social or "Construtora")[:40]
        qr = qr_totp_svg(segredo, u.email, emissor)
    return render_template("auth/seguranca.html", qr=qr, segredo=segredo)


@bp_auth.route("/atividades")
@login_required
def atividades():
    if not current_user.is_admin:
        abort(403)
    busca = request.args.get("busca", "")
    q = Atividade.query
    if busca:
        like = f"%{busca}%"
        q = q.filter(or_(Atividade.acao.ilike(like), Atividade.detalhe.ilike(like), Atividade.usuario.ilike(like)))
    return render_template("auth/atividades.html", atividades=q.order_by(Atividade.id.desc()).limit(500).all(),
                           busca=busca)


@bp_auth.route("/backup")
@login_required
def backup():
    if not current_user.is_admin:
        abort(403)
    pasta = current_app.config.get("BACKUP_FOLDER")
    existentes = []
    if pasta and os.path.isdir(pasta):
        for nome in sorted(os.listdir(pasta), reverse=True):
            if nome.startswith("backup-") and nome.endswith(".zip"):
                existentes.append((nome, os.path.getsize(os.path.join(pasta, nome))))
    return render_template("auth/backup.html", existentes=existentes[:60])


@bp_auth.route("/backup/baixar", methods=["POST"])
@login_required
def backup_baixar():
    """Gera um backup na hora e baixa (banco + todos os anexos)."""
    if not current_user.is_admin:
        abort(403)
    tmp = tempfile.mkdtemp()
    caminho = gerar_backup(current_app, tmp)
    registrar_atividade("Baixou um backup completo")
    resp = send_file(caminho, as_attachment=True, download_name=os.path.basename(caminho))
    resp.call_on_close(lambda: shutil.rmtree(tmp, ignore_errors=True))
    return resp


@bp_auth.route("/backup/arquivo/<nome>")
@login_required
def backup_arquivo(nome):
    if not current_user.is_admin:
        abort(403)
    pasta = current_app.config.get("BACKUP_FOLDER")
    nome = os.path.basename(nome)
    if not pasta or not (nome.startswith("backup-") and nome.endswith(".zip")):
        abort(404)
    registrar_atividade("Baixou um backup", nome)
    return send_from_directory(pasta, nome, as_attachment=True)


# ---------------------------------------------------------------- Helpers

def totais_por_obra():
    """Retorna {obra_id: {'entrada': Decimal, 'saida': Decimal}} (obra_id None = empresa geral)."""
    linhas = (
        db.session.query(Lancamento.obra_id, Lancamento.tipo, func.sum(Lancamento.valor_centavos))
        .group_by(Lancamento.obra_id, Lancamento.tipo)
        .all()
    )
    res = {}
    for obra_id, tipo, total in linhas:
        res.setdefault(obra_id, {"entrada": cent(0), "saida": cent(0)})[tipo] = cent(total)
    return res


def _soma(query, tipo):
    total = query.filter(Lancamento.tipo == tipo).with_entities(func.sum(Lancamento.valor_centavos)).scalar()
    return cent(total)


def obras_opcoes():
    return Obra.query.order_by(Obra.status != "Em andamento", Obra.nome).all()


# ---------------------------------------------------------------- Painel

@bp_main.route("/")
@login_required
def dashboard():
    hoje = date.today()
    inicio_mes = hoje.replace(day=1)
    q_mes = Lancamento.query.filter(Lancamento.data >= inicio_mes, Lancamento.data <= hoje)
    q_total = Lancamento.query

    resumo = {
        "entradas_mes": _soma(q_mes, "entrada"),
        "saidas_mes": _soma(q_mes, "saida"),
        "entradas_total": _soma(q_total, "entrada"),
        "saidas_total": _soma(q_total, "saida"),
    }
    resumo["saldo_mes"] = resumo["entradas_mes"] - resumo["saidas_mes"]
    resumo["saldo_total"] = resumo["entradas_total"] - resumo["saidas_total"]

    totais = totais_por_obra()
    obras = Obra.query.filter(Obra.status.in_(["Em andamento", "Planejada", "Pausada"])).order_by(Obra.nome).all()
    geral = totais.get(None, {"entrada": cent(0), "saida": cent(0)})

    contratos_vencendo = (
        Contrato.query.filter(
            Contrato.status == "Vigente",
            Contrato.data_fim.isnot(None),
            Contrato.data_fim <= hoje + timedelta(days=30),
        )
        .order_by(Contrato.data_fim)
        .all()
    )
    ultimos = Lancamento.query.order_by(Lancamento.data.desc(), Lancamento.id.desc()).limit(10).all()

    folha_mes = cent(
        db.session.query(func.sum(PagamentoFuncionario.valor_centavos))
        .filter(PagamentoFuncionario.data_pagamento >= inicio_mes)
        .scalar()
    )

    docs_vencendo = (
        Documento.query.filter(Documento.validade.isnot(None), Documento.validade <= hoje + timedelta(days=30))
        .order_by(Documento.validade).limit(15).all()
    )
    pedidos_abertos = (
        Pedido.query.filter(Pedido.status.notin_(PEDIDO_STATUS_FINAIS))
        .order_by(Pedido.previsao_entrega.is_(None), Pedido.previsao_entrega).limit(10).all()
    )
    vendas_ativas = Venda.query.filter(Venda.status != "Distratada").all()
    a_receber = sum((v.a_receber for v in vendas_ativas), cent(0))

    return render_template(
        "dashboard.html", docs_vencendo=docs_vencendo, pedidos_abertos=pedidos_abertos, a_receber=a_receber,
        resumo=resumo, obras=obras, totais=totais, geral=geral,
        contratos_vencendo=contratos_vencendo, ultimos=ultimos, hoje=hoje,
        folha_mes=folha_mes, funcionarios_ativos=Funcionario.query.filter_by(ativo=True).count(),
    )


# ---------------------------------------------------------------- Arquivos

@bp_main.route("/arquivo/<path:nome>")
@login_required
def arquivo(nome):
    nome = os.path.basename(nome)
    original = None
    for modelo in (Lancamento, NotaFiscal, Contrato, PagamentoFuncionario, Documento):
        obj = modelo.query.filter_by(arquivo=nome).first()
        if obj:
            original = obj.arquivo_nome
            break
    if original is None:
        abort(404)
    baixar = request.args.get("baixar") == "1"
    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"], nome, as_attachment=baixar, download_name=original
    )


# ---------------------------------------------------------------- Empresa

@bp_main.route("/empresa", methods=["GET", "POST"])
@login_required
def empresa():
    emp = Empresa.get()
    if request.method == "POST":
        for campo in ("razao_social", "nome_fantasia", "cnpj", "inscricao_estadual",
                      "endereco", "telefone", "email", "responsavel"):
            setattr(emp, campo, request.form.get(campo, "").strip())
        db.session.commit()
        flash("Dados da empresa salvos.", "success")
        return redirect(url_for("main.empresa"))
    return render_template(
        "empresa/form.html", emp=emp, docs=Documento.query.filter_by(entidade="empresa")
        .order_by(Documento.categoria, Documento.titulo).all(),
        categorias_doc=CATEGORIAS_DOCUMENTO["empresa"], hoje=date.today(),
    )


# ---------------------------------------------------------------- Obras

@bp_main.route("/obras")
@login_required
def obras():
    status = request.args.get("status", "")
    q = Obra.query
    if status:
        q = q.filter_by(status=status)
    return render_template(
        "obras/lista.html", obras=q.order_by(Obra.nome).all(), totais=totais_por_obra(),
        status=status, status_opcoes=OBRA_STATUS,
    )


@bp_main.route("/obras/nova", methods=["GET", "POST"])
@bp_main.route("/obras/<int:id>/editar", methods=["GET", "POST"])
@login_required
def obra_form(id=None):
    obra = db.get_or_404(Obra, id) if id else Obra(status="Em andamento")
    if request.method == "POST":
        try:
            obra.nome = request.form.get("nome", "").strip()
            if not obra.nome:
                raise ValueError("Informe o nome da obra.")
            obra.cliente = request.form.get("cliente", "").strip()
            obra.endereco = request.form.get("endereco", "").strip()
            obra.orcamento = parse_valor(request.form.get("orcamento"))
            obra.data_inicio = parse_data(request.form.get("data_inicio"))
            obra.previsao_termino = parse_data(request.form.get("previsao_termino"))
            obra.status = request.form.get("status") or "Em andamento"
            obra.observacoes = request.form.get("observacoes", "")
        except ValueError as e:
            flash(str(e), "danger")
            return render_sem_salvar(render_template, "obras/form.html", obra=obra, status_opcoes=OBRA_STATUS)
        db.session.add(obra)
        db.session.commit()
        flash("Obra salva.", "success")
        return redirect(url_for("main.obra_detalhe", id=obra.id))
    return render_template("obras/form.html", obra=obra, status_opcoes=OBRA_STATUS)


@bp_main.route("/obras/<int:id>")
@login_required
def obra_detalhe(id):
    obra = db.get_or_404(Obra, id)
    q = Lancamento.query.filter_by(obra_id=id)
    entradas, saidas = _soma(q, "entrada"), _soma(q, "saida")
    por_categoria = (
        db.session.query(Lancamento.categoria, func.sum(Lancamento.valor_centavos))
        .filter(Lancamento.obra_id == id, Lancamento.tipo == "saida")
        .group_by(Lancamento.categoria)
        .order_by(func.sum(Lancamento.valor_centavos).desc())
        .all()
    )
    return render_template(
        "obras/detalhe.html",
        obra=obra, entradas=entradas, saidas=saidas,
        por_categoria=[(c or "Sem categoria", cent(v)) for c, v in por_categoria],
        lancamentos=q.order_by(Lancamento.data.desc(), Lancamento.id.desc()).all(),
        notas=NotaFiscal.query.filter_by(obra_id=id).order_by(NotaFiscal.data_emissao.desc()).all(),
        contratos=Contrato.query.filter_by(obra_id=id).order_by(Contrato.data_inicio.desc()).all(),
        funcionarios=Funcionario.query.filter_by(obra_id=id, ativo=True).order_by(Funcionario.nome).all(),
        pagamentos=PagamentoFuncionario.query.filter_by(obra_id=id)
        .order_by(PagamentoFuncionario.data_pagamento.desc()).all(),
        vendas=Venda.query.filter_by(obra_id=id).order_by(Venda.unidade).all(),
        pedidos=Pedido.query.filter_by(obra_id=id).order_by(Pedido.data_pedido.desc()).all(),
        docs=Documento.query.filter_by(entidade="obra", entidade_id=id)
        .order_by(Documento.categoria, Documento.titulo).all(),
        categorias_doc=CATEGORIAS_DOCUMENTO["obra"], hoje=date.today(),
    )


@bp_main.route("/obras/<int:id>/excluir", methods=["POST"])
@login_required
def obra_excluir(id):
    obra = db.get_or_404(Obra, id)
    vinculos = sum(
        m.query.filter_by(obra_id=id).count()
        for m in (Lancamento, NotaFiscal, Contrato, PagamentoFuncionario, Funcionario, Venda, Pedido)
    ) + Documento.query.filter_by(entidade="obra", entidade_id=id).count()
    if vinculos:
        flash("Essa obra possui lançamentos, documentos, vendas ou funcionários vinculados. "
              "Para mantê-la no histórico, altere o status para 'Concluída' ou 'Cancelada'.", "warning")
        return redirect(url_for("main.obra_detalhe", id=id))
    db.session.delete(obra)
    db.session.commit()
    flash("Obra excluída.", "success")
    return redirect(url_for("main.obras"))


# ---------------------------------------------------------------- Financeiro

def _filtrar_lancamentos():
    f = {k: request.args.get(k, "") for k in ("obra", "tipo", "categoria", "de", "ate", "busca", "fornecedor", "cliente")}
    q = Lancamento.query
    if f["obra"] == "geral":
        q = q.filter(Lancamento.obra_id.is_(None))
    elif f["obra"]:
        q = q.filter(Lancamento.obra_id == parse_int(f["obra"]))
    if f["fornecedor"]:
        q = q.filter(Lancamento.fornecedor_id == parse_int(f["fornecedor"]))
    if f["cliente"]:
        q = q.filter(Lancamento.cliente_id == parse_int(f["cliente"]))
    if f["tipo"] in ("entrada", "saida"):
        q = q.filter(Lancamento.tipo == f["tipo"])
    if f["categoria"]:
        q = q.filter(Lancamento.categoria == f["categoria"])
    try:
        if f["de"]:
            q = q.filter(Lancamento.data >= parse_data(f["de"]))
        if f["ate"]:
            q = q.filter(Lancamento.data <= parse_data(f["ate"]))
    except ValueError:
        flash("Data de filtro inválida.", "warning")
    if f["busca"]:
        q = q.filter(Lancamento.descricao.ilike(f"%{f['busca']}%"))
    return q, f


@bp_main.route("/financeiro")
@login_required
def financeiro():
    q, filtros = _filtrar_lancamentos()
    entradas, saidas = _soma(q, "entrada"), _soma(q, "saida")
    lancamentos = q.order_by(Lancamento.data.desc(), Lancamento.id.desc()).all()
    return render_template(
        "financeiro/lista.html", lancamentos=lancamentos, filtros=filtros,
        entradas=entradas, saidas=saidas, obras=obras_opcoes(),
        fornecedores=Fornecedor.query.order_by(Fornecedor.nome).all(),
        clientes=Cliente.query.order_by(Cliente.nome).all(),
        categorias=CATEGORIAS_ENTRADA + CATEGORIAS_SAIDA,
    )


@bp_main.route("/financeiro/exportar.csv")
@login_required
def financeiro_csv():
    q, _ = _filtrar_lancamentos()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Data", "Tipo", "Descrição", "Categoria", "Obra", "Fornecedor", "Cliente",
                "Forma de pagamento", "Valor", "Origem"])
    for l in q.order_by(Lancamento.data, Lancamento.id).all():
        valor = f"{l.valor:.2f}".replace(".", ",")
        w.writerow([
            formata_data(l.data), "Entrada" if l.tipo == "entrada" else "Saída", l.descricao,
            l.categoria, l.obra.nome if l.obra else "Empresa (geral)",
            l.fornecedor.nome_exibicao if l.fornecedor else "", l.cliente.nome if l.cliente else "",
            l.forma_pagamento,
            valor if l.tipo == "entrada" else "-" + valor, l.origem,
        ])
    # BOM para o Excel reconhecer acentos
    return Response(
        "﻿" + buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=lancamentos.csv"},
    )


@bp_main.route("/financeiro/novo", methods=["GET", "POST"])
@bp_main.route("/financeiro/<int:id>/editar", methods=["GET", "POST"])
@login_required
def lancamento_form(id=None):
    if id:
        l = db.get_or_404(Lancamento, id)
        if l.nota_id:
            flash("Esse lançamento foi gerado por uma nota fiscal. Edite a nota.", "info")
            return redirect(url_for("cad.nota_form", id=l.nota_id))
        if l.pagamento_id:
            flash("Esse lançamento foi gerado por um pagamento de funcionário. Edite o pagamento.", "info")
            return redirect(url_for("cad.pagamento_form", id=l.pagamento_id))
    else:
        l = Lancamento(
            tipo=request.args.get("tipo", "saida"), data=date.today(),
            obra_id=parse_int(request.args.get("obra")),
            fornecedor_id=parse_int(request.args.get("fornecedor")),
            cliente_id=parse_int(request.args.get("cliente")),
        )
        pedido = db.session.get(Pedido, parse_int(request.args.get("pedido")) or 0)
        if pedido:
            l.tipo, l.pedido_id, l.fornecedor_id, l.obra_id = "saida", pedido.id, pedido.fornecedor_id, pedido.obra_id
            l.descricao = f"Pagamento pedido {pedido.numero or ''} – {pedido.descricao}".replace("  ", " ")
            l.valor = max(pedido.valor - pedido.pago, cent(0))
        venda = db.session.get(Venda, parse_int(request.args.get("venda")) or 0)
        if venda:
            l.tipo, l.venda_id, l.cliente_id, l.obra_id = "entrada", venda.id, venda.cliente_id, venda.obra_id
            l.categoria = "Venda de unidade / Parcela de cliente"
            l.descricao = f"Recebimento {venda.unidade} – {venda.cliente.nome}".strip()
    if request.method == "POST":
        try:
            l.tipo = request.form.get("tipo")
            if l.tipo not in ("entrada", "saida"):
                raise ValueError("Escolha se é entrada ou saída.")
            l.descricao = request.form.get("descricao", "").strip()
            if not l.descricao:
                raise ValueError("Informe a descrição.")
            l.valor = parse_valor(request.form.get("valor"))
            if l.valor <= 0:
                raise ValueError("Informe um valor maior que zero.")
            l.data = parse_data(request.form.get("data")) or date.today()
            l.categoria = request.form.get("categoria", "")
            l.forma_pagamento = request.form.get("forma_pagamento", "")
            l.obra_id = parse_int(request.form.get("obra_id"))
            l.fornecedor_id = parse_int(request.form.get("fornecedor_id"))
            l.cliente_id = parse_int(request.form.get("cliente_id"))
            l.venda_id = parse_int(request.form.get("venda_id"))
            l.pedido_id = parse_int(request.form.get("pedido_id"))
            pedido = db.session.get(Pedido, l.pedido_id) if l.pedido_id else None
            if pedido:
                l.fornecedor_id = l.fornecedor_id or pedido.fornecedor_id
                l.obra_id = l.obra_id or pedido.obra_id
            venda = db.session.get(Venda, l.venda_id) if l.venda_id else None
            if venda:
                l.cliente_id = venda.cliente_id
                l.obra_id = l.obra_id or venda.obra_id
            salvar_anexo(l)
        except ValueError as e:
            flash(str(e), "danger")
            return render_sem_salvar(_render_lancamento, l)
        db.session.add(l)
        db.session.commit()
        flash("Lançamento salvo.", "success")
        if request.form.get("continuar"):
            return redirect(url_for("main.lancamento_form", tipo=l.tipo, obra=l.obra_id or ""))
        return redirect(url_segura(request.args.get("voltar")) or url_for("main.financeiro"))
    return _render_lancamento(l)


def _render_lancamento(l):
    return render_template(
        "financeiro/form.html", l=l, obras=obras_opcoes(),
        fornecedores=Fornecedor.query.filter(
            or_(Fornecedor.ativo.is_(True), Fornecedor.id == l.fornecedor_id)).order_by(Fornecedor.nome).all(),
        clientes=Cliente.query.order_by(Cliente.nome).all(),
        vendas=Venda.query.join(Cliente).order_by(Cliente.nome, Venda.unidade).all(),
        pedidos=Pedido.query.filter(or_(Pedido.status.notin_(PEDIDO_STATUS_FINAIS), Pedido.id == l.pedido_id))
        .order_by(Pedido.data_pedido.desc()).all(),
        categorias_entrada=CATEGORIAS_ENTRADA, categorias_saida=CATEGORIAS_SAIDA,
        formas=FORMAS_PAGAMENTO,
    )


@bp_main.route("/financeiro/<int:id>/excluir", methods=["POST"])
@login_required
def lancamento_excluir(id):
    l = db.get_or_404(Lancamento, id)
    if l.nota_id or l.pagamento_id:
        flash("Esse lançamento é automático. Exclua a nota fiscal ou o pagamento de origem.", "warning")
        return redirect(url_for("main.financeiro"))
    remover_anexo(l.arquivo)
    db.session.delete(l)
    db.session.commit()
    flash("Lançamento excluído.", "success")
    return redirect(url_segura(request.form.get("voltar")) or url_for("main.financeiro"))


# ---------------------------------------------------------------- Relatórios

@bp_main.route("/relatorios")
@login_required
def relatorios():
    hoje = date.today()
    ano = parse_int(request.args.get("ano")) or hoje.year
    inicio, fim = date(ano, 1, 1), date(ano, 12, 31)
    base = db.session.query(Lancamento).filter(Lancamento.data >= inicio, Lancamento.data <= fim)

    # Mês a mês
    mensal = {m: {"entrada": cent(0), "saida": cent(0)} for m in range(1, 13)}
    for l_data, tipo, valor in base.with_entities(Lancamento.data, Lancamento.tipo, Lancamento.valor_centavos):
        mensal[l_data.month][tipo] += cent(valor)

    # Por categoria
    por_cat = (
        base.with_entities(Lancamento.tipo, Lancamento.categoria, func.sum(Lancamento.valor_centavos))
        .group_by(Lancamento.tipo, Lancamento.categoria)
        .order_by(func.sum(Lancamento.valor_centavos).desc())
        .all()
    )
    # Por obra
    por_obra_raw = (
        base.with_entities(Lancamento.obra_id, Lancamento.tipo, func.sum(Lancamento.valor_centavos))
        .group_by(Lancamento.obra_id, Lancamento.tipo)
        .all()
    )
    nomes = {o.id: o.nome for o in Obra.query.all()}
    por_obra = {}
    for obra_id, tipo, total in por_obra_raw:
        nome = nomes.get(obra_id, "Empresa (geral)")
        por_obra.setdefault(nome, {"entrada": cent(0), "saida": cent(0)})[tipo] = cent(total)

    anos = sorted({d.year for (d,) in db.session.query(Lancamento.data).all()} | {hoje.year}, reverse=True)
    return render_template(
        "relatorios.html", ano=ano, anos=anos, mensal=mensal,
        entradas_cat=[(c or "Sem categoria", cent(v)) for t, c, v in por_cat if t == "entrada"],
        saidas_cat=[(c or "Sem categoria", cent(v)) for t, c, v in por_cat if t == "saida"],
        por_obra=sorted(por_obra.items()),
    )
