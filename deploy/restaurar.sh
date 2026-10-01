#!/usr/bin/env bash
# Restaura um backup (.zip gerado pelo sistema) no servidor.
# Serve também para LEVAR OS DADOS do computador para o servidor:
# no sistema do computador, vá em  Usuário > Backup > Gerar e baixar backup,
# envie o .zip para o servidor e rode:
#     bash /opt/construtora/app/deploy/restaurar.sh /root/backup-AAAA-MM-DD_HHMMSS.zip
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Rode como root (ou com sudo)."; exit 1; }
ZIP="${1:-}"
[[ -f "$ZIP" ]] || { echo "Uso: bash restaurar.sh /caminho/do/backup.zip"; exit 1; }
DADOS=/var/lib/construtora
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python3 - "$ZIP" "$TMP" <<'EOF'
import sys, zipfile, os
z = zipfile.ZipFile(sys.argv[1])
for n in z.namelist():
    # Só extrai o que é esperado (evita caminhos maliciosos dentro do zip)
    if n == "instance/construtora.db" or (n.startswith("instance/uploads/") and "/" not in n[len("instance/uploads/"):] and ".." not in n):
        z.extract(n, sys.argv[2])
if not os.path.exists(os.path.join(sys.argv[2], "instance/construtora.db")):
    sys.exit("Esse arquivo não parece um backup do sistema (falta instance/construtora.db).")
EOF

echo "==> Guardando uma cópia dos dados atuais antes de substituir"
if [[ -f "$DADOS/construtora.db" ]]; then
  systemctl start construtora-backup.service || true
fi

systemctl stop construtora.service
cp "$TMP/instance/construtora.db" "$DADOS/construtora.db"
mkdir -p "$DADOS/uploads"
if [[ -d "$TMP/instance/uploads" ]]; then
  rsync -a "$TMP/instance/uploads/" "$DADOS/uploads/"
fi
chown -R construtora:construtora "$DADOS"
chmod -R u+rwX,go-rwx "$DADOS"
systemctl start construtora.service
echo "Backup restaurado! Entre no sistema com o mesmo e-mail e senha de antes."
