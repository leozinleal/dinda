"""Backup do sistema: banco de dados + arquivos anexados em um único .zip.

Uso no servidor (agendado todo dia pelo instalador):
    python -m app.backup /caminho/da/pasta/de/backups [dias_para_manter]
"""
import os
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta


def _caminho_sqlite(uri):
    if not uri.startswith("sqlite:///"):
        raise RuntimeError("O backup automático só funciona com o banco SQLite padrão.")
    return uri[len("sqlite:///"):]


def gerar_backup(app, destino):
    """Cria backup-AAAA-MM-DD_HHMM.zip em `destino` e retorna o caminho do arquivo."""
    os.makedirs(destino, exist_ok=True)
    nome = f"backup-{datetime.now():%Y-%m-%d_%H%M%S}.zip"
    caminho_zip = os.path.join(destino, nome)
    banco = _caminho_sqlite(app.config["SQLALCHEMY_DATABASE_URI"])
    uploads = app.config["UPLOAD_FOLDER"]

    with tempfile.TemporaryDirectory() as tmp:
        # Cópia consistente do banco, mesmo com o sistema em uso
        copia = os.path.join(tmp, "construtora.db")
        origem = sqlite3.connect(banco)
        alvo = sqlite3.connect(copia)
        with alvo:
            origem.backup(alvo)
        origem.close()
        alvo.close()

        parcial = caminho_zip + ".parcial"
        with zipfile.ZipFile(parcial, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(copia, "instance/construtora.db")
            if os.path.isdir(uploads):
                for nome_arq in sorted(os.listdir(uploads)):
                    caminho = os.path.join(uploads, nome_arq)
                    if os.path.isfile(caminho):
                        z.write(caminho, f"instance/uploads/{nome_arq}")
            z.writestr("LEIA-ME.txt", (
                "Backup do sistema de gestão da construtora.\n"
                f"Gerado em {datetime.now():%d/%m/%Y %H:%M}.\n\n"
                "Para restaurar: pare o sistema, descompacte este arquivo dentro da pasta do sistema\n"
                "(substituindo a pasta instance/) e inicie o sistema de novo.\n"
            ))
        os.replace(parcial, caminho_zip)
    return caminho_zip


def limpar_antigos(destino, dias):
    limite = datetime.now() - timedelta(days=dias)
    for nome in os.listdir(destino):
        caminho = os.path.join(destino, nome)
        if nome.startswith("backup-") and nome.endswith(".zip"):
            if datetime.fromtimestamp(os.path.getmtime(caminho)) < limite:
                os.remove(caminho)


if __name__ == "__main__":
    from app import create_app

    pasta = sys.argv[1] if len(sys.argv) > 1 else "backups"
    dias = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    aplicacao = create_app()
    arquivo = gerar_backup(aplicacao, pasta)
    limpar_antigos(pasta, dias)
    print(f"Backup criado: {arquivo}")
