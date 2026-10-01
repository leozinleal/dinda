#!/usr/bin/env bash
# Atualiza o sistema no servidor para uma versão nova, mantendo todos os dados.
#
# Uso (como root, de dentro da pasta da versão nova descompactada):
#     bash deploy/atualizar.sh
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Rode como root (ou com sudo)."; exit 1; }
ORIGEM="$(cd "$(dirname "$0")/.." && pwd)"
APP=/opt/construtora/app

echo "==> Fazendo um backup antes de atualizar"
systemctl start construtora-backup.service

echo "==> Copiando a versão nova"
rsync -a --delete --exclude '.venv' --exclude 'instance' --exclude '.git' --exclude '__pycache__' \
  --exclude 'tests' "$ORIGEM/" "$APP/"
/opt/construtora/venv/bin/pip install -q -r "$APP/requirements.txt"
chown -R root:root "$APP"

echo "==> Reiniciando"
systemctl restart construtora.service
sleep 3
systemctl is-active --quiet construtora.service && echo "Atualizado com sucesso!" \
  || { echo "O sistema não iniciou. Veja: journalctl -u construtora -n 50"; exit 1; }
