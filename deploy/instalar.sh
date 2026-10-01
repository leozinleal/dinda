#!/usr/bin/env bash
# Instala o sistema num servidor Ubuntu 22.04 ou 24.04 novo, com HTTPS automático.
#
# Uso (como root, de dentro da pasta do sistema descompactada):
#     bash deploy/instalar.sh sistema.suaconstrutora.com.br
#
# O que este script faz:
#   - atualiza o servidor e liga as atualizações de segurança automáticas
#   - instala Python, Caddy (HTTPS automático com Let's Encrypt), firewall e fail2ban
#   - copia o sistema para /opt/construtora e cria o serviço que liga sozinho
#   - guarda os dados em /var/lib/construtora e os backups diários em /var/backups/construtora
#   - mostra no final o CÓDIGO DE INSTALAÇÃO pedido no primeiro acesso
set -euo pipefail

DOMINIO="${1:-}"
if [[ -z "$DOMINIO" ]]; then
  echo "Uso: bash deploy/instalar.sh sistema.suaconstrutora.com.br"; exit 1
fi
if [[ $EUID -ne 0 ]]; then
  echo "Rode como root (ou com sudo)."; exit 1
fi
ORIGEM="$(cd "$(dirname "$0")/.." && pwd)"
APP=/opt/construtora/app
DADOS=/var/lib/construtora
BACKUPS=/var/backups/construtora
ENVFILE=/etc/construtora.env
USUARIO=construtora

passo() { echo; echo "==> $*"; }

passo "Atualizando o servidor (pode demorar alguns minutos)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get -y -q upgrade
apt-get install -y -q python3 python3-venv rsync curl gnupg ufw fail2ban unattended-upgrades \
  debian-keyring debian-archive-keyring apt-transport-https
dpkg-reconfigure -f noninteractive unattended-upgrades

passo "Instalando o Caddy (servidor web com HTTPS automático)"
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q
  apt-get install -y -q caddy
fi

passo "Criando usuário e pastas do sistema"
id -u "$USUARIO" >/dev/null 2>&1 || useradd --system --home /opt/construtora --shell /usr/sbin/nologin "$USUARIO"
mkdir -p "$APP" "$DADOS/uploads" "$BACKUPS"
rsync -a --delete --exclude '.venv' --exclude 'instance' --exclude '.git' --exclude '__pycache__' \
  --exclude 'tests' "$ORIGEM/" "$APP/"
python3 -m venv /opt/construtora/venv
/opt/construtora/venv/bin/pip install -q --upgrade pip
/opt/construtora/venv/bin/pip install -q -r "$APP/requirements.txt"
chown -R root:root /opt/construtora
chown -R "$USUARIO:$USUARIO" "$DADOS" "$BACKUPS"
chmod 750 "$DADOS" "$BACKUPS"

passo "Gerando configuração e chaves secretas"
if [[ ! -f "$ENVFILE" ]]; then
  SETUP_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(4).upper())')"
  cat > "$ENVFILE" <<EOF
PRODUCAO=1
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
SETUP_TOKEN=$SETUP_TOKEN
DATABASE_URL=sqlite:///$DADOS/construtora.db
UPLOAD_FOLDER=$DADOS/uploads
BACKUP_FOLDER=$BACKUPS
HOST=127.0.0.1
PORT=8000
INATIVIDADE_MINUTOS=60
EOF
fi
chown root:"$USUARIO" "$ENVFILE"
chmod 640 "$ENVFILE"
SETUP_TOKEN="$(grep '^SETUP_TOKEN=' "$ENVFILE" | cut -d= -f2)"

passo "Criando o serviço do sistema"
cat > /etc/systemd/system/construtora.service <<EOF
[Unit]
Description=Sistema de gestão da construtora
After=network.target

[Service]
User=$USUARIO
Group=$USUARIO
WorkingDirectory=$APP
EnvironmentFile=$ENVFILE
ExecStart=/opt/construtora/venv/bin/python run.py
Restart=always
RestartSec=3
# Isolamento: o sistema só consegue escrever nas pastas de dados e backups
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DADOS $BACKUPS
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
UMask=0077

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/construtora-backup.service <<EOF
[Unit]
Description=Backup diário do sistema da construtora

[Service]
Type=oneshot
User=$USUARIO
WorkingDirectory=$APP
EnvironmentFile=$ENVFILE
ExecStart=/opt/construtora/venv/bin/python -m app.backup $BACKUPS 30
ReadWritePaths=$DADOS $BACKUPS
ProtectSystem=strict
PrivateTmp=true
EOF

cat > /etc/systemd/system/construtora-backup.timer <<EOF
[Unit]
Description=Backup diário às 3h da manhã

[Timer]
OnCalendar=*-*-* 03:15:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

passo "Configurando o HTTPS para $DOMINIO"
cat > /etc/caddy/Caddyfile <<EOF
$DOMINIO {
	encode gzip
	request_body {
		max_size 30MB
	}
	header {
		-Server
	}
	reverse_proxy 127.0.0.1:8000
}
EOF

passo "Ligando o firewall (só SSH, HTTP e HTTPS ficam abertos)"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
systemctl enable --now fail2ban >/dev/null 2>&1 || true

passo "Iniciando tudo"
systemctl daemon-reload
systemctl enable --now construtora.service construtora-backup.timer
systemctl restart construtora.service
systemctl reload caddy || systemctl restart caddy
sleep 3
if ! systemctl is-active --quiet construtora.service; then
  echo "O sistema não iniciou. Veja o erro com: journalctl -u construtora -n 50"; exit 1
fi

echo
echo "=================================================================="
echo " Instalação concluída!"
echo
echo " Endereço:  https://$DOMINIO"
echo " Código de instalação (pedido no primeiro acesso):  $SETUP_TOKEN"
echo
echo " Se o endereço ainda não abrir, aguarde alguns minutos: o DNS e o"
echo " certificado HTTPS podem levar um tempo para ficar prontos."
echo "=================================================================="
