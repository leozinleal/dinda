"""Recursos de segurança: verificação em duas etapas (TOTP), limite de tentativas de login,
política de senha, expiração por inatividade, cabeçalhos HTTP e registro de atividades."""
import base64
import hashlib
import hmac
import io
import secrets
import struct
import time
from datetime import datetime, timedelta
from urllib.parse import quote

from flask import current_app, flash, redirect, request, session, url_for
from flask_login import current_user, logout_user

from .models import Atividade, TentativaLogin, db

# ---------------------------------------------------------------- Senha

SENHA_MINIMA = 10


def validar_senha(senha, email=""):
    """Retorna uma mensagem de erro, ou None se a senha for aceitável."""
    if len(senha) < SENHA_MINIMA:
        return f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres."
    if senha.isdigit() or senha.isalpha():
        return "Use letras e números (ou símbolos) na senha."
    if email and senha.lower() in email.lower():
        return "A senha não pode ser parecida com o e-mail."
    if senha.lower() in {"1234567890", "senha12345", "construtora1", "qwerty1234", "abc1234567"}:
        return "Essa senha é muito comum. Escolha outra."
    return None


# ---------------------------------------------------------------- Verificação em duas etapas (TOTP)

def novo_segredo_totp():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _codigo_totp(segredo, passo):
    chave = base64.b32decode(segredo + "=" * (-len(segredo) % 8))
    h = hmac.new(chave, struct.pack(">Q", passo), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def verificar_totp(segredo, codigo, ultimo_passo=None):
    """Confere o código de 6 dígitos (aceita 30s de diferença no relógio).
    Retorna o passo usado (para impedir reutilização) ou None se inválido."""
    codigo = "".join(c for c in (codigo or "") if c.isdigit())
    if not segredo or len(codigo) != 6:
        return None
    agora = int(time.time()) // 30
    for passo in (agora - 1, agora, agora + 1):
        if ultimo_passo is not None and passo <= ultimo_passo:
            continue
        if hmac.compare_digest(_codigo_totp(segredo, passo), codigo):
            return passo
    return None


def qr_totp_svg(segredo, email, emissor):
    import qrcode
    import qrcode.image.svg

    uri = (f"otpauth://totp/{quote(emissor)}:{quote(email)}?secret={segredo}"
           f"&issuer={quote(emissor)}&digits=6&period=30")
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode()


# ---------------------------------------------------------------- Limite de tentativas

MAX_FALHAS_IP = 10       # por IP, na janela
MAX_FALHAS_EMAIL = 5     # por conta, na janela
JANELA_MINUTOS = 15


def ip_cliente():
    return (request.remote_addr or "")[:64]


def login_bloqueado(email):
    """True se houve falhas demais recentemente para este IP ou e-mail."""
    desde = datetime.utcnow() - timedelta(minutes=JANELA_MINUTOS)
    q = TentativaLogin.query.filter(TentativaLogin.sucesso.is_(False), TentativaLogin.criado_em >= desde)
    if q.filter(TentativaLogin.ip == ip_cliente()).count() >= MAX_FALHAS_IP:
        return True
    return bool(email) and q.filter(TentativaLogin.email == email).count() >= MAX_FALHAS_EMAIL


def registrar_tentativa(email, sucesso):
    db.session.add(TentativaLogin(ip=ip_cliente(), email=(email or "")[:120], sucesso=sucesso))
    if sucesso:
        # Login correto zera as falhas daquela conta
        TentativaLogin.query.filter_by(email=email, sucesso=False).delete()
    # Limpeza de registros antigos
    TentativaLogin.query.filter(TentativaLogin.criado_em < datetime.utcnow() - timedelta(days=30)).delete()
    db.session.commit()


# ---------------------------------------------------------------- Registro de atividades

ROTULOS = {
    "obra": "obra", "lancamento": "lançamento financeiro", "nota": "nota fiscal", "contrato": "contrato",
    "funcionario": "funcionário", "pagamento": "pagamento de funcionário", "cliente": "cliente",
    "venda": "venda", "fornecedor": "fornecedor", "pedido": "pedido", "documento": "documento",
}


def registrar_atividade(acao, detalhe=""):
    usuario = current_user.nome if current_user.is_authenticated else ""
    db.session.add(Atividade(usuario=usuario, ip=ip_cliente(), acao=acao[:120], detalhe=(detalhe or "")[:500]))
    db.session.commit()


def descrever_requisicao():
    """Transforma um POST bem-sucedido (ex.: 'cad.nota_excluir', id=3) em texto legível."""
    endpoint = (request.endpoint or "").split(".")[-1]
    ident = (request.view_args or {}).get("id")
    if endpoint == "documento_novo":
        qtd = len([a for a in request.files.getlist("arquivos") if a.filename])
        return "Anexou documento(s)", f"{qtd} arquivo(s) em {request.form.get('entidade', '')}"
    if endpoint == "pedido_acompanhamento":
        return "Atualizou pedido", f"pedido #{ident}: {request.form.get('status', '')}"
    for chave, rotulo in ROTULOS.items():
        if endpoint.startswith(chave):
            if endpoint.endswith("_excluir"):
                return f"Excluiu {rotulo}", f"#{ident}"
            if endpoint.endswith("_form"):
                return (f"Editou {rotulo}", f"#{ident}") if ident else (f"Criou {rotulo}", "")
    return endpoint.replace("_", " ").capitalize(), (f"#{ident}" if ident else "")


# ---------------------------------------------------------------- Ganchos da aplicação

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
    "font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
SEM_LOG = {"auth.login", "auth.login_codigo", "auth.logout", "auth.setup", "auth.minha_senha",
           "auth.seguranca"}


def configurar(app):
    producao = app.config.get("PRODUCAO")
    app.config.setdefault("INATIVIDADE_MINUTOS", 60)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=bool(producao),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    )

    @app.before_request
    def _inatividade():
        if not current_user.is_authenticated:
            return None
        agora = int(time.time())
        ultimo = session.get("ultimo_acesso", agora)
        limite = current_app.config["INATIVIDADE_MINUTOS"] * 60
        if agora - ultimo > limite:
            logout_user()
            session.clear()
            flash("Sua sessão expirou por inatividade. Entre novamente.", "warning")
            return redirect(url_for("auth.login", next=request.full_path if request.method == "GET" else None))
        session["ultimo_acesso"] = agora
        session.permanent = True
        return None

    @app.after_request
    def _depois(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if resp.mimetype == "text/html":
            resp.headers.setdefault("Content-Security-Policy", CSP)
            resp.headers.setdefault("Cache-Control", "no-store")
        if producao:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        # Registro de atividades: só ações que deram certo (redirecionam depois de salvar)
        if (request.method == "POST" and resp.status_code in (302, 303) and current_user.is_authenticated
                and request.endpoint not in SEM_LOG):
            try:
                acao, detalhe = descrever_requisicao()
                registrar_atividade(acao, detalhe)
            except Exception:  # o registro nunca pode impedir o uso do sistema
                db.session.rollback()
        return resp
