#!/bin/sh
# macOS: dê dois cliques neste arquivo no Finder para iniciar o sistema.
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python não encontrado. Instale em https://www.python.org/downloads/ e tente de novo."
  read -r _; exit 1
fi
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
(sleep 3; open http://localhost:8000) &
.venv/bin/python run.py
