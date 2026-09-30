#!/usr/bin/env sh
# Linux / macOS: instala as dependências (na primeira vez) e inicia o sistema.
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python run.py
