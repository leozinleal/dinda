import os
import secrets
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import abort, current_app, request, session
from werkzeug.utils import secure_filename

EXTENSOES_PERMITIDAS = {
    "pdf", "xml", "jpg", "jpeg", "png", "gif", "webp", "heic",
    "doc", "docx", "xls", "xlsx", "odt", "ods", "csv", "txt", "zip",
}


def parse_valor(texto) -> Decimal:
    """Aceita '1.234,56', '1234,56', '1234.56', 'R$ 1.234,56'."""
    if texto is None:
        return Decimal("0")
    s = str(texto).replace("R$", "").replace(" ", "").strip()
    if not s:
        return Decimal("0")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError(f"Valor inválido: {texto}")


def parse_data(texto):
    if not texto:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Data inválida: {texto}")


def parse_int(texto):
    try:
        return int(texto) if texto else None
    except ValueError:
        return None


def formata_moeda(valor) -> str:
    if valor is None:
        valor = Decimal("0")
    valor = Decimal(valor)
    sinal = "-" if valor < 0 else ""
    inteiro, dec = f"{abs(valor):,.2f}".split(".")
    return f"{sinal}R$ {inteiro.replace(',', '.')},{dec}"


def formata_data(d) -> str:
    if not d:
        return ""
    if isinstance(d, (date, datetime)):
        return d.strftime("%d/%m/%Y")
    return str(d)


def gravar_arquivo(arquivo):
    """Grava um arquivo enviado na pasta de anexos. Retorna (nome_em_disco, nome_original)."""
    nome_original = arquivo.filename
    ext = nome_original.rsplit(".", 1)[-1].lower() if "." in nome_original else ""
    if ext not in EXTENSOES_PERMITIDAS:
        raise ValueError(
            f"Tipo de arquivo não permitido ({nome_original}). Use: " + ", ".join(sorted(EXTENSOES_PERMITIDAS))
        )
    nome_disco = f"{uuid.uuid4().hex}.{ext}"
    arquivo.save(os.path.join(current_app.config["UPLOAD_FOLDER"], nome_disco))
    # Mantém acentos no nome original (usado só para exibição/download), sem partes de caminho.
    nome_limpo = os.path.basename(nome_original.replace("\\", "/")).strip()[:200]
    return nome_disco, nome_limpo or secure_filename(nome_original) or nome_disco


def salvar_anexo(obj, campo="arquivo"):
    """Salva o arquivo enviado no formulário (se houver) e grava no objeto. Remove o anterior."""
    arquivo = request.files.get(campo)
    if not arquivo or not arquivo.filename:
        if request.form.get("remover_arquivo") and obj.arquivo:
            remover_anexo(obj.arquivo)
            obj.arquivo = None
            obj.arquivo_nome = None
        return
    nome_disco, nome_original = gravar_arquivo(arquivo)
    if obj.arquivo:
        remover_anexo(obj.arquivo)
    obj.arquivo = nome_disco
    obj.arquivo_nome = nome_original


def remover_anexo(nome_disco):
    if not nome_disco:
        return
    caminho = os.path.join(current_app.config["UPLOAD_FOLDER"], os.path.basename(nome_disco))
    if os.path.exists(caminho):
        os.remove(caminho)


# --- Proteção CSRF simples (token na sessão, conferido em todo POST) ---

def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def verificar_csrf():
    if request.method == "POST" and not current_app.config.get("TESTING_SKIP_CSRF"):
        token = request.form.get("_csrf")
        if not token or token != session.get("_csrf"):
            abort(400, "Token de segurança inválido. Recarregue a página e tente novamente.")


def cent(centavos) -> Decimal:
    return Decimal(centavos or 0) / 100


def url_segura(url):
    """Só aceita redirecionamentos para caminhos internos do próprio sistema."""
    if url and url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return None


def render_sem_salvar(render, *args, **kwargs):
    """Renderiza o formulário com os dados digitados após um erro, sem gravar nada no banco."""
    from .models import db

    with db.session.no_autoflush:
        html = render(*args, **kwargs)
    db.session.rollback()
    return html
