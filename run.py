"""Inicia o sistema. Depois acesse http://localhost:5000 no navegador."""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 5000))
    if os.environ.get("FLASK_DEBUG") == "1":
        app.run(host=host, port=port, debug=True)
    else:
        from waitress import serve

        print(f"Sistema rodando em http://{'localhost' if host == '127.0.0.1' else host}:{port}")
        serve(app, host=host, port=port)
